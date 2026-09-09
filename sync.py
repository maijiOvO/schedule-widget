# -*- coding: utf-8 -*-
"""把改动推到 Google Drive 上的远程仓库，顺便验证远程没被同步搞坏。

    python _schedule/sync.py                # 推送
    python _schedule/sync.py -m "改了什么"   # 先提交再推送
    python _schedule/sync.py --pull         # 从远程拉下来
    python _schedule/sync.py --check        # 只验证远程完整性

为什么要专门写这个：Drive 是流式盘，`git push` 会往远程写几十个小对象文件，
Drive 异步上传，中间状态可能不一致 —— ref 更新了但对象没写全。表现是下次
push 报 "unresolved deltas"，更糟的是在另一台机器 clone 时才发现仓库是坏的。
（2026-09-09 就这么坏过一次。）

所以每次推完都做两件事：gc 成单个 pack 文件（Drive 同步一个大文件比几十个
小文件可靠得多），然后 fsck 验一遍。发现坏了就自动重建远程再推一次。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REMOTE = "drive"


def git(*args, repo=REPO, quiet=False, **kw):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, **kw)
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    if out and not quiet:
        print(out)
    return r.returncode, out


def remote_url():
    code, url = git("remote", "get-url", REMOTE, quiet=True)
    if code:
        print(f"没有名叫 {REMOTE} 的远程仓库。先建一个：")
        print('  git remote add drive "G:/我的云端硬盘/Study.git"')
        return None
    return url


def check(url):
    """远程对象库是否完整"""
    r = subprocess.run(["git", "--git-dir", url, "fsck", "--no-progress"],
                       capture_output=True)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    bad = [l for l in out.splitlines()
           if l.startswith("error") or "invalid sha1" in l or "missing" in l]
    return (not bad), bad


def pack(url):
    """把散落的小对象合并成一个 pack —— Drive 同步大文件比小文件可靠"""
    subprocess.run(["git", "--git-dir", url, "gc", "--quiet"], capture_output=True)


def rebuild(url):
    """远程坏了就地重建。本地是完整的源，远程只是副本，删了不丢东西。"""
    broken = url.rstrip("/\\") + ".broken"
    print(f"远程仓库损坏，重建中（旧的挪到 {os.path.basename(broken)}）")
    if os.path.exists(broken):
        import shutil
        shutil.rmtree(broken, ignore_errors=True)
    os.rename(url, broken)
    subprocess.run(["git", "init", "--bare", "--quiet", url], check=True)


def push(url, branch):
    code, _ = git("push", REMOTE, branch)
    if code == 0:
        pack(url)
        ok, bad = check(url)
        if ok:
            return True
        print("推上去了但远程校验没过：", *bad[:3], sep="\n  ")
    rebuild(url)
    code, _ = git("push", REMOTE, branch)
    if code:
        return False
    pack(url)
    ok, bad = check(url)
    if not ok:
        print("重建后还是坏的，可能是 Drive 正在同步 —— 过一会再跑一次")
        return False
    return True


def main():
    url = remote_url()
    if not url:
        return 1
    if not os.path.exists(url):
        print(f"远程路径不存在：{url}")
        print("Google Drive 装了吗？同步完了吗？")
        return 1

    _, branch = git("rev-parse", "--abbrev-ref", "HEAD", quiet=True)

    if "--check" in sys.argv:
        ok, bad = check(url)
        print("远程完整 ✓" if ok else "远程损坏 ✗")
        for l in bad[:5]:
            print("  ", l)
        return 0 if ok else 1

    if "--pull" in sys.argv:
        ok, bad = check(url)
        if not ok:
            print("远程是坏的，别从它拉。在有完整仓库的那台机器上跑一次 sync.py")
            return 1
        return git("pull", REMOTE, branch)[0]

    if "-m" in sys.argv:
        msg = sys.argv[sys.argv.index("-m") + 1]
        git("add", "-A")
        code, _ = git("commit", "-m", msg)
        if code:
            print("（没有需要提交的改动）")

    _, dirty = git("status", "--porcelain", quiet=True)
    if dirty:
        print("有未提交的改动，只推已提交的部分：")
        print("  " + "\n  ".join(dirty.splitlines()[:8]))

    print(f"推送 {branch} → {url}")
    if push(url, branch):
        _, head = git("rev-parse", "--short", "HEAD", quiet=True)
        print(f"完成，远程和本地都在 {head}")
        return 0
    print("推送失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
