# Player Khadas

Player offline per gli export `LYRICS_PROMPTER/` dell'editor. Non legge o
modifica testo: conserva soltanto l'ultima scaletta Khadas completamente
verificata, per poterla riusare al successivo avvio.

Il monitor e le pagine sono orizzontali (1680×1050). La scaletta presenta
20 voci per pagina in due colonne di 10: Prev/Next scorrono prima la colonna
sinistra dall'alto al basso e poi quella destra. Una pressione lunga di
Prev/Next passa alla pagina precedente/successiva dell'elenco.
Tenere insieme Prev e Next per tre secondi apre il menu di spegnimento.
Prev/Next scelgono Annulla o Spegni; Select conferma. La selezione
iniziale è Annulla. Da tastiera USB si può aprire lo stesso menu con `F12`.
Durante una copia da USB il menu resta disabilitato.

## Importazione durante prove e live

Nella scaletta, tenere Select/Menu premuto per 900 ms apre la richiesta di
nuova importazione: Prev annulla, Next conferma. Il clic breve di Select
apre il brano al rilascio. Nel brano Select torna al menu; inserire una USB
durante la visualizzazione non apre finestre e non avvia importazioni.

Sono compatibili sia l'export singolo `LYRICS_PROMPTER/manifest.json`, sia
più export raccolti in cartelle:

```
LYRICS_PROMPTER/
  Serata completa/
    manifest.json
    songs/
    opening.png
  Set acustico/
    manifest.json
    songs/
```

La locandina è facoltativa. I nomi delle cartelle identificano le liste.
Con una sola lista si importa direttamente; con più liste Prev/Next
selezionano e Select conferma. L'ultima voce è Annulla. Si copia e verifica
soltanto il pacchetto selezionato, in un thread separato dall'interfaccia.
Errori e annullamenti conservano la lista e la selezione precedenti.

L'USB viene montata su richiesta con `ro,nosuid,nodev,noexec`, senza dialoghi
di sistema, e smontata al termine o all'annullamento. Un mount preesistente
in scrittura viene rifiutato. La schermata finale distingue lo smontaggio
riuscito da quello fallito; Select apre la nuova scaletta. Una lista sola
rimane salvata sul dispositivo, anche dopo lo spegnimento.

## Contratto `manifest.json` v1

```json
{
  "schema": "lyrics-prompter/khadas-list",
  "version": 1,
  "display": { "width": 1680, "height": 1050 },
  "opening": { "path": "opening.png", "sha256": "<64 caratteri esadecimali>" },
  "songs": [
    {
      "id": "song-123-baila-morena",
      "title": "Baila Morena",
      "artist": "Zucchero",
      "pages": [
        {
          "path": "songs/song-123-baila-morena/page-001.png",
          "sha256": "<64 caratteri esadecimali>"
        }
      ]
    }
  ]
}
```

`opening` può essere `null`. Ogni pagina deve essere un PNG 1680×1050 e deve
avere un percorso numerato consecutivamente (`page-001.png`, `page-002.png`,
ecc.). Il player copia prima l'intero pacchetto in una cache temporanea,
verifica manifest, struttura, checksum e dimensioni, poi attiva la lista.
Un errore non sostituisce la lista già attiva.
Le vecchie scalette 1050×1680 non sono più accettate; occorre esportarle
nuovamente in orizzontale.

```bash
python3 player.py --usb-root /percorso/della/chiavetta
```

Per verificare un pacchetto senza aprire l'interfaccia:

```bash
python3 player.py --usb-root /percorso/della/chiavetta --check
python3 -m unittest -v test_player.py
```

Comandi: `PgSu`/sinistra = Prev, `Invio`/spazio = Select/Menu,
`PgGiù`/destra = Next. Sul Khadas questi tasti saranno associati ai tre
pulsanti fisici.

## Mount automatico una tantum

Sul Khadas dedicato eseguire una sola volta, inserendo la password locale,
questo comando:

```bash
pkexec /home/khadas/lyrics-prompter/khadas-player/install-usb-mount-policy.sh
```

Da quel momento il player può montare USB FAT/exFAT tramite UDisks senza
password e senza finestre durante il live.
