# Lyrics Prompter — Prompter offline

Player Khadas VIM1S per scalette esportate dall'editor Sites: visualizza
esclusivamente PNG statiche 1050×1680, senza impaginazione o accesso Internet.

## Componenti

- `khadas-player/`: player GTK 3, importazione USB e test.
- `boot-setup/`: avvio silenzioso e sessione grafica dedicata al player.
- `pedale-3-pulsanti/`: prototipo CircuitPython e schemi di cablaggio.

## Funzionamento

All'avvio si può scegliere se usare l'ultima scaletta salvata o importarne
una da USB. Il dispositivo conserva soltanto l'ultima scaletta verificata.
Gli export singoli e le cartelle contenenti più scalette sono entrambi
supportati; dettagli in `khadas-player/README.md`.

Prev/Next navigano tra pagine e brani. Select apre un brano e torna alla
scaletta. Nella scaletta, tenere Prev/Next premuto cambia pagina di elenco;
tenere Select premuto per circa un secondo apre la richiesta di importazione.
L'inserimento di una USB durante un brano non interrompe la visualizzazione.

## Verifiche

```sh
python3 -m unittest discover -s khadas-player -v
```

Il controllo grafico `khadas-player/check_import_layout.py` va eseguito
manualmente sul display del Prompter e mostra brevemente una schermata di
prova. Non importa dalla chiavetta e non modifica la scaletta salvata.

## Installazione e arresto

Gli script di `boot-setup/` sono specifici del VIM1S configurato con utente
`khadas` e percorso `/home/khadas/lyrics-prompter`. Non sono un installer
generico. `install-boot.py` configura l'avvio Linux e l'autostart;
`install-kiosk.py` aggiunge la sessione dedicata e il logo nero. Richiedono
privilegi amministrativi e salvano gli originali con uno script di ripristino
in `/var/backups/lyrics-prompter-boot/`.

La sessione rilancia il player se termina, ma non rileva un processo congelato.
PWR premuto brevemente richiede l'arresto di Linux: sul dispositivo di prova
è stato osservato un arresto registrato seguito da una nuova accensione.
Attendere il completamento dell'arresto prima di scollegare l'alimentazione.
RESET non esegue un arresto ordinato.

## Limiti noti

Il codice della pedaliera è un prototipo: usa `keyboard.send`, quindi invia
un clic completo alla pressione e non mantiene il tasto premuto fino al
rilascio fisico. Prima di usarlo con i comandi prolungati del player occorre
adattare e collaudare la gestione di pressione/rilascio sul pedale reale.
La navigazione e le pressioni prolungate del player sono state provate con
una tastiera USB. È ancora raccomandata una prova prolungata con l'hardware
definitivo prima dell'uso in concerto.
