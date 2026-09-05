#!/bin/sh
printf 'PROMPTER - configurazione avvio silenzioso\n\nInserisci qui la password amministratore del Prompter.\n'
sudo /usr/bin/python3 /home/khadas/lyrics-prompter/boot-setup/install-kiosk.py
printf '\nPremi Invio per chiudere.\n'
read answer
