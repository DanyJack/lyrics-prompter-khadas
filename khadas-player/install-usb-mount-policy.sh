#!/bin/sh
# Run once through pkexec on the dedicated Khadas player.
set -eu

install -d -m 755 /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/60-lyrics-prompter-usb.rules <<'RULE'
// Dedicated offline player: permit only the local player account to mount USB
// filesystems through UDisks, without interactive authentication during a live.
polkit.addRule(function(action, subject) {
    if (subject.user == "khadas" &&
        action.id == "org.freedesktop.udisks2.filesystem-mount") {
        return polkit.Result.YES;
    }
});
RULE
chmod 644 /etc/polkit-1/rules.d/60-lyrics-prompter-usb.rules
