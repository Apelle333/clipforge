# Iniziare con CLIPFORGE su Windows

È una versione alpha funzionante: controlla sempre parole, tagli e sottotitoli.
Non servono abbonamenti o API a pagamento. Il marketplace non è implementato.

1. Installa Python 3.12 con launcher, Node.js LTS, FFmpeg **full** e Ollama.
   Trovi i collegamenti nel README. FFmpeg e ffprobe devono essere nel PATH.
2. Scarica lo ZIP del repository, estrailo e apri PowerShell nella cartella.
3. Esegui:

```powershell
.\Install-CLIPFORGE.ps1 -CheckOnly
.\Install-CLIPFORGE.ps1
.\Launch-CLIPFORGE.ps1
```

Non è un'installazione in un clic: i prerequisiti sono manuali. L'installer
prepara un ambiente Python isolato e scarica modelli gratuiti. Se le policy
bloccano gli script, non usare Bypass: segui le regole del PC o i comandi
manuali in INSTALLATION.md.

Senza NVIDIA usa `-Cpu` sia per installare sia per avviare. L'elaborazione può
essere molto più lenta. Il browser apre http://127.0.0.1:8078; Ctrl+C ferma il server.

Importa un MP4/MOV/WebM locale. In Settings scegli **Italian** per parlato
interamente italiano e controlla il modello Ollama. Genera le clip, poi verifica
le proposte: il voto AI è soggettivo. Clicca le parole sbagliate per correggerle,
salva, regola inizio/fine e scegli sottotitoli e inquadratura. **Fit** conserva
l'intera scena; **Manual** consente un crop statico. **Render exact preview**
mostra il vero MP4: il draft è approssimato. Esporta e scarica il file finale.

Le correzioni conservano i tempi delle parole. La punteggiatura proposta non
riscrive il lessico, ma richiede ascolto e revisione. Per nuovi titoli e ranking
usa la ri-analisi, che crea un nuovo job. Non viene certificata l'accuratezza ASR.

I nuovi dati privati si trovano in `%LOCALAPPDATA%\CLIPFORGE`; le installazioni
esistenti mantengono la propria cartella. Non pubblicare video, database,
trascrizioni o log personali nelle issue. Non esporre il backend su Internet.
