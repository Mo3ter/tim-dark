"""启动 TIM 3.4.8 并在初始化前应用图片路径修复，磁盘 DLL 保持原样。"""
import argparse
import json
import pathlib
import threading
import sys
import contextlib
import traceback

from patch_paste_path import ORIGINAL, SITE, build, layout


def runtime_plan(data, directory):
    result = build(data, directory)
    offset, cave, cave_rva, available = layout(data)
    # 包含末尾 UTF-16 NUL；使用与静态补丁相同的指令和路径。
    length = 38 + len((directory + "\0").encode("utf-16-le"))
    return {"site": SITE, "original": list(ORIGINAL),
            "patch": list(result[offset:offset + 8]), "cave": cave_rva,
            "body": list(result[cave:cave + length])}


def injection_source(plan):
    return "const plan=" + json.dumps(plan) + ";" + r"""
Process.attachModuleObserver({onAdded(m) {
    if (m.name.toLowerCase() !== 'kernelutil.dll') return;
    try {
        const site = m.base.add(plan.site);
        const bytes = Array.from(new Uint8Array(site.readByteArray(8)));
        if (bytes.join(',') !== plan.original.join(','))
            throw Error('Loaded KernelUtil.dll instructions do not match');
        Memory.patchCode(m.base.add(plan.cave), plan.body.length,
                         p => p.writeByteArray(plan.body));
        Memory.patchCode(site, plan.patch.length, p => p.writeByteArray(plan.patch));
        send({ready: true});
    } catch (e) { send({error: String(e)}); }
}});
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tim-dir", required=True)
    ap.add_argument("--appdata-dir", required=True)
    ap.add_argument("--background", action="store_true", help="保留 TIM 的 /background 后台启动方式")
    args = ap.parse_args()
    root = pathlib.Path(args.tim_dir).resolve()
    directory = str(pathlib.Path(args.appdata_dir).resolve())
    if not (pathlib.Path(directory) / "Tencent").is_dir():
        raise SystemExit("实际 AppData 下没有原有 Tencent 数据目录")
    dll = root / "Bin" / "KernelUtil.dll"
    data = dll.read_bytes()
    plan = runtime_plan(data, directory)
    backup = dll.with_name(dll.name + ".paste-path.orig")
    if backup.exists() and backup.read_bytes() != data:
        raise SystemExit("请先用 patch_paste_path.py --revert 还原磁盘 DLL")
    import frida  # 仅启动器需要；python -m pip install frida
    device = frida.get_local_device()
    if any(p.name.lower() == "tim.exe" for p in device.enumerate_processes()):
        raise SystemExit("请先退出正在运行的 TIM，再使用此启动器")
    done = threading.Event()
    errors = []
    command = [str(root / "Bin" / "TIM.exe")]
    if args.background:
        command.append("/background")
    pid = device.spawn(command, cwd=str(root / "Bin"))
    session = None
    resumed = False
    try:
        session = device.attach(pid)
        script = session.create_script(injection_source(plan))

        def receive(message, _data):
            payload = message.get("payload", {})
            if message.get("type") == "error" or payload.get("error"):
                errors.append(payload.get("error") or message.get("description"))
                done.set()
            elif payload.get("ready"):
                done.set()

        script.on("message", receive)
        script.load()
        device.resume(pid)
        resumed = True
        if not done.wait(30):
            raise RuntimeError("30 秒内没有加载 KernelUtil.dll，路径补丁未应用")
        if errors:
            raise RuntimeError("; ".join(errors))
        print("TIM 图片路径修复已在启动阶段应用；磁盘 DLL 未修改")
    finally:
        if not resumed:
            device.resume(pid)
        if session is not None:
            session.detach()


if __name__ == "__main__":
    if sys.stdout is None:
        # pythonw 自启没有终端，保留本地启动结果及失败信息。
        with pathlib.Path(__file__).with_suffix(".log").open("a", encoding="utf-8") as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                try:
                    main()
                except BaseException:
                    traceback.print_exc()
                    raise
    else:
        main()
