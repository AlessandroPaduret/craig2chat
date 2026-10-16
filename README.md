# craig2chat

Trasforma una registrazione di [Craig](https://craig.chat) (il bot che registra le chiamate Discord) in una **chat in stile WhatsApp**: chi ha detto cosa e quando, in ordine.

Craig salva una traccia audio separata per ogni persona. `craig2chat` trascrive ogni traccia con [Whisper](https://github.com/SYSTRAN/faster-whisper), poi intreccia le frasi di tutti in ordine di tempo e crea:

- **`chat.html`**: la conversazione come chat, con bolle, nomi colorati e orari (si apre nel browser, funziona anche offline e in tema scuro)
- **`chat.txt`**: la stessa conversazione in testo semplice

```
SW2 Corporation · #General

[19:02:52] flamaster06895: Eh, però dovremmo parlare.
[19:02:53] kilo123b: Bra bra bra bra bra bra bra bra
[19:02:54] davidebaraldo: Beh, sì, ma è bello il progetto, cioè, molto figo, dai, ci sta, bello, dai, dai, dai, dai che si va, andiamo.
```

La trascrizione avviene tutta sul tuo computer: l'audio non viene mandato da nessuna parte.

## Requisiti

- [uv](https://docs.astral.sh/uv/): installa da solo Python e le librerie al primo avvio
- [ffmpeg](https://ffmpeg.org/): decodifica l'audio

Su Arch/CachyOS: `sudo pacman -S uv ffmpeg`. Su Debian/Ubuntu: `sudo apt install ffmpeg` e poi `curl -LsSf https://astral.sh/uv/install.sh | sh`.

## Installazione

```sh
git clone https://github.com/AlessandroPaduret/craig2chat.git
ln -s "$PWD/craig2chat/craig2chat" ~/.local/bin/craig2chat
```

(`~/.local/bin` deve essere nel `PATH`.) In alternativa lancialo direttamente con `./craig2chat`.

## Uso

1. Da Craig scarica la registrazione in formato **AAC** (o FLAC, Ogg…) con **una traccia per persona**. Va bene sia lo ZIP sia la cartella estratta.
2. Lancia:

```sh
craig2chat ~/Scaricati/craig-XXXXXXXX.aac
```

I file `chat.html` e `chat.txt` finiscono dentro la cartella. Se gli dai uno ZIP, finiscono in una cartella `<nome-zip>-chat` accanto allo zip.

### Opzioni

| Opzione | Cosa fa |
|---|---|
| `-o CARTELLA` | dove salvare `chat.html` e `chat.txt` |
| `--model NOME` | modello Whisper: `tiny`, `base`, `small`, `medium`, `large-v3` (default). Più grande = più preciso ma più lento |
| `--lang it` | lingua parlata (default `it`) |
| `--rename vecchio=Nuovo` | dà un nome leggibile a un parlante, ripetibile: `--rename kilo123b=Kilo --rename davidebaraldo=Davide` |
| `--skip nome` | ignora una traccia, per esempio un bot musicale |
| `--threads N` | thread della CPU da usare (default: tutti) |

Esempio completo:

```sh
craig2chat craig-abc123.zip --model medium --rename kilo123b=Kilo --skip musicbot -o ~/Documenti/riunione
```

## Come funziona

1. **Tracce.** Cerca tutti i file audio nella cartella (o nello zip). Il nome del parlante viene dal nome del file: `2-kilo123b.aac` → `kilo123b`.
2. **Trascrizione.** Ogni traccia viene trascritta con faster-whisper, con il tempo di ogni parola. Il filtro VAD salta i silenzi.
3. **Frasi.** Le parole di ogni persona vengono raggruppate in frasi: una frase si chiude alla punteggiatura finale (`. ! ?`) o dopo una pausa di più di 0,8 secondi.
4. **Ordine.** Craig mantiene tutte le tracce sincronizzate tra loro, anche per chi entra in ritardo, quindi basta ordinare le frasi di tutti per tempo di inizio. Se due persone parlano sopra, le frasi restano intere.
5. **Bolle.** Frasi consecutive della stessa persona a meno di 2 secondi di distanza finiscono nella stessa bolla.
6. **Orari.** L'ora di inizio viene letta da `info.txt` di Craig. Ogni messaggio mostra il minuto della registrazione e l'ora reale (nel fuso orario del computer).

Le due soglie (`PAUSE` e `GAP`) sono costanti in cima allo script, se vuoi bolle più corte o più lunghe.

## Velocità

Gira sulla CPU (o sulla GPU NVIDIA, se c'è CUDA). Con `large-v3` su CPU una chiamata lunga può richiedere parecchio tempo. Per una prova veloce usa `--model small`, che però sbaglia più parole. Il modello viene scaricato al primo uso (circa 3 GB per `large-v3`).

## Limiti

- Whisper a volte inventa o storpia parole su audio molto breve, rumori o versi.
- La punteggiatura la decide Whisper, quindi i confini delle frasi non sono sempre perfetti.
