# -*- coding: utf-8 -*-
"""把桌面组件打包成不需要 Python 的 exe。

    python _schedule/build_exe.py

产物是 _schedule/日程组件.exe，单文件、无控制台。

注意：日程数据会被编译进 exe。改了 data.py 之后必须重新跑本脚本，
否则 exe 里还是旧数据。有 Python 的机器优先用 安装到这台电脑.bat。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "日程组件"
EXE = os.path.join(HERE, NAME + ".exe")


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("先装 PyInstaller：  python -m pip install pyinstaller")
        return 1

    build = os.path.join(HERE, ".build")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",              # 单个 exe，方便拷来拷去
        "--windowed",             # 不要控制台窗口
        "--name", NAME,
        "--distpath", HERE,       # 直接产在 _schedule/ 下
        "--workpath", build,
        "--specpath", build,
        "--noconfirm",
        # 只留组件真正用到的，砍掉体积
        "--exclude-module", "PIL",
        "--exclude-module", "numpy",
        "--exclude-module", "unittest",
        "--exclude-module", "pydoc",
        "--exclude-module", "email",
        "--exclude-module", "http",
        "--exclude-module", "xml",
        os.path.join(HERE, "widget.py"),
    ]
    print("打包中，大概一两分钟 ...")
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        print("打包失败")
        return r.returncode

    shutil.rmtree(build, ignore_errors=True)
    if os.path.exists(EXE):
        print(f"\n好了：{EXE}  ({os.path.getsize(EXE) / 1048576:.1f} MB)")
        print("双击就能跑，不需要 Python。设开机自启：在命令行跑一次")
        print(f'  "{EXE}" --startup')
    return 0


if __name__ == "__main__":
    sys.exit(main())
