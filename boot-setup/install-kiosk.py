#!/usr/bin/python3
import datetime
import os
from pathlib import Path
import shutil
import struct
import subprocess

if os.geteuid() != 0:
    raise SystemExit('Eseguire con sudo.')
base = Path('/home/khadas/lyrics-prompter/boot-setup')
for program in ('xfwm4', 'xprop', 'xsetroot', 'flock'):
    if not shutil.which(program):
        raise SystemExit(f'Componente assente: {program}')
backup = Path('/var/backups/lyrics-prompter-boot') / ('kiosk-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
restore = ['#!/bin/sh', 'set -eu']

def replace(target, data):
    target = Path(target)
    copy = backup / str(len(restore))
    if target.exists():
        shutil.copy2(target, copy)
        restore.append(f'cp -p {copy} {target}')
    else:
        restore.append(f'rm -f {target}')
    temp = target.with_name(target.name + '.prompter-new')
    if target.exists():
        shutil.copy2(target, temp)
    temp.write_bytes(data if isinstance(data, bytes) else data.encode())
    temp.chmod(0o644)
    os.replace(temp, target)
    (backup / 'restore.sh').write_text('\n'.join(restore) + '\nsync\n')

# Fresh, plain black Windows BMP matching the documented U-Boot format.
width = height = 500
pixels = bytes(((width * 3 + 3) // 4 * 4) * height)
bmp = struct.pack('<2sIHHI', b'BM', 54 + len(pixels), 0, 0, 54)
bmp += struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24, 0, len(pixels), 2834, 2834, 0, 0)
replace('/usr/share/fenix/logo/logo.bmp', bmp + pixels)
replace('/usr/share/xsessions/prompter.desktop', '[Desktop Entry]\nName=Prompter\nType=Application\nExec=/home/khadas/lyrics-prompter/boot-setup/prompter-session.sh\nDesktopNames=Prompter\n')
replace('/etc/lightdm/lightdm.conf.d/60-prompter-kiosk.conf', '[Seat:*]\nautologin-user=khadas\nautologin-user-timeout=0\nautologin-session=prompter\nuser-session=prompter\nxserver-command=X -background none -nocursor\n')
mask = Path('/etc/systemd/system/getty@tty1.service')
if not mask.exists() and not mask.is_symlink():
    restore.append('systemctl unmask getty@tty1.service')
    (backup / 'restore.sh').write_text('\n'.join(restore) + '\nsync\n')
    subprocess.run(['systemctl', 'mask', 'getty@tty1.service'], check=True)
os.sync()
(base / 'kiosk-installed.txt').write_text(f'Installato. Ripristino: {backup}/restore.sh\n')
print(f'Installato. Ripristino: sudo sh {backup}/restore.sh')
