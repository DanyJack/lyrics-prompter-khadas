#!/usr/bin/python3
"""Install reversible quiet Linux boot; does not flash firmware or reboot."""
import datetime
import os
from pathlib import Path
import re
import shutil

if os.geteuid() != 0:
    raise SystemExit('Eseguire con sudo.')
base = Path('/home/khadas/lyrics-prompter/boot-setup')
uenv = Path('/boot/uEnv.txt')
extlinux = Path('/boot/extlinux/extlinux.conf')
old_uenv = uenv.read_text()
old_extlinux = extlinux.read_text()
if '${boot_user_args}' not in old_extlinux or not re.search(r'^consoles=', old_uenv, re.M):
    raise SystemExit('Configurazione boot inattesa: nessuna modifica.')
new_uenv = re.sub(r'^(consoles=.*) console=tty0\b', r'\1', old_uenv, flags=re.M)
flags = 'quiet loglevel=0 systemd.show_status=false rd.systemd.show_status=false vt.global_cursor_default=0 logo.nologo'
if not re.search(r'^boot_user_args=', new_uenv, re.M):
    raise SystemExit('boot_user_args assente: nessuna modifica.')
new_uenv = re.sub(r'^boot_user_args=(.*)$', lambda m: 'boot_user_args=' + m[1].strip() + ' ' + flags, new_uenv, flags=re.M)
new_extlinux = re.sub(r'^menu background .*\n', '', old_extlinux, flags=re.M)
# U-Boot PXE timeout is measured in tenths of a second. Avoid zero,
# which may mean an unlimited wait in some bootloader versions.
new_extlinux = re.sub(r'^timeout .*$', 'timeout 1', new_extlinux, flags=re.M)
backup = Path('/var/backups/lyrics-prompter-boot') / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup.mkdir(parents=True)
changes = {
    uenv: new_uenv,
    extlinux: new_extlinux,
    Path('/home/khadas/.config/autostart/lyrics-prompter-display.desktop'): (base / 'lyrics-prompter-display.desktop').read_text(),
}
restore = ['#!/bin/sh', 'set -eu']
for index, (target, content) in enumerate(changes.items()):
    copy = backup / str(index)
    shutil.copy2(target, copy)
    restore.append(f'cp -p {copy} {target}')
    temporary = target.with_name(target.name + '.prompter-new')
    shutil.copy2(target, temporary)
    temporary.write_text(content)
    os.chown(temporary, target.stat().st_uid, target.stat().st_gid)
    os.replace(temporary, target)
(backup / 'restore.sh').write_text('\n'.join(restore) + '\nsync\n')
os.sync()
(base / 'installed.txt').write_text(f'Configurazione installata. Backup: {backup}\n')
print(f'Configurazione installata. Backup e ripristino: {backup}/restore.sh')
print('Riavvio da eseguire dopo la verifica.')
