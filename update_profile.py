"""Refreshes the published Throne profile from the router's live rules.

Run on the home PC: python update_profile.py
Reads /etc/sing-box/config.json from the router over SSH, rebuilds
cudy-rules.json, and pushes it to github.com/Ivantech123/throne-rules
if anything changed. Throne picks it up on its next profile update.
"""
import getpass
import json
import os
import subprocess
import sys
import urllib.request

import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "publish")
PW_FILE = os.path.expandvars(
    r"%LOCALAPPDATA%\Temp\claude\C--Users-Ivan\8e7e5c4d-55c8-42ed-a663-e0de4068d921\scratchpad\router.pw")
sys.path.insert(0, HERE)
from make_profile import convert  # noqa: E402


def router_config():
    pw = open(PW_FILE).read().strip() if os.path.exists(PW_FILE) else getpass.getpass("Router root password: ")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.1.1", username="root", password=pw, timeout=10, look_for_keys=False, allow_agent=False)
    _, o, _ = c.exec_command("cat /etc/sing-box/config.json")
    data = json.loads(o.read().decode())
    c.close()
    return data


def main():
    prof = convert(router_config())
    path = os.path.join(REPO, "cudy-rules.json")
    new = json.dumps(prof, ensure_ascii=False, indent=2)
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    if new == old:
        print("No changes.")
        return
    open(path, "w", encoding="utf-8", newline="\n").write(new)
    git = ["git", "-C", REPO, "-c", "user.name=Ivantech123", "-c", "user.email=Ivantech123@users.noreply.github.com"]
    subprocess.run(git + ["add", "cudy-rules.json"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "Update rules from router"], check=True)
    subprocess.run(git + ["push", "-q"], check=True)
    # jsDelivr caches for up to a day; ask it to drop the old copy now.
    urllib.request.urlopen("https://purge.jsdelivr.net/gh/Ivantech123/throne-rules@main/cudy-rules.json", timeout=20)
    print(f"Published {len(prof['rules'])} rules.")


if __name__ == "__main__":
    main()
