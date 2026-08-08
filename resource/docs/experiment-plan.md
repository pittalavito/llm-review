# Piano sperimentale — llm-review 2.0

Protocollo per la campagna sperimentale della tesi. Esecuzione manuale dalla UI;
ogni run va etichettato nel campo **description** con la convenzione sotto, che è
ciò che permette di ritrovare e raggruppare i run a posteriori (senza runner
automatico è l'unica chiave di raggruppamento).

## Convenzione di etichettatura dei run

```
<RQ>|<paper-tag>|<config>|rep<N>
es.:  RQ1|p03|summary+tool|rep2
```

- `RQ0` = collaudo mock, `RQ1` = strategie di contesto, `RQ2` = modelli, `RQ3` = comitato.
- `paper-tag`: p01..p10 (mappa paper_id → tag tenuta in una tabellina a parte).
- `config`: vedi tabelle sotto.
- `repN`: ripetizione 1..3.

## Dataset (10 paper, ICLR 2026)

- Fonte: **ICLR 2026** via loader OpenReview dell'app. Motivazione anti-contaminazione:
  le review sono state scritte dopo il cutoff di conoscenza di tutti i modelli
  candidati (GPT-4o ~ott 2023, locali ~2023, Claude ~2025), quindi nessun modello
  può "ricordare" giudizi o esiti. ICLR inoltre tiene pubbliche anche le submission
  rifiutate con le loro review — indispensabile per il bilanciamento.
- **5 accettati + 5 rifiutati**, con review umane complete (rating + confidence +
  sub-score soundness/presentation/contribution).
- Paper "piccoli": indicativamente sotto le 10 pagine / ~40k caratteri di testo estratto
  (verificabile dopo l'upload dall'indice full_context in Redis) — così il full_context
  resta economico e il summarizer non tronca mai.
- Per ogni paper annotare: paper_id, tag (p01..p10), esito umano, rating medio umano,
  e la **data del primo preprint arXiv** (caveat contaminazione da citare in tesi:
  preferire paper con preprint successivo al cutoff più recente).

## Fase 0 — Collaudo (mock, costo zero) ← SIAMO QUI

Obiettivo: validare protocollo e strumentazione, non i risultati.

1. Caricare i 10 paper OpenReview e verificare nel comparator che le review umane
   siano parsate correttamente (rating, confidence, sub-score, decisione).
2. Per 2-3 paper, eseguire un run mock per ciascuna configurazione di RQ1
   (etichetta `RQ0|...`): verificare che summary venga generato e cachato,
   che il tool_trace compaia nei dettagli tecnici, che i token siano registrati.
3. Prova del comparator su un run mock (i numeri non significano nulla, conta
   che la dashboard aggreghi correttamente).
4. Uscita di fase: checklist verde su upload, indicizzazione, 4 configurazioni,
   persistenza e comparator.

## RQ1 — Strategia di contesto (fattore principale)

*Come cambiano qualità e costo della review al variare dell'accesso al paper?*

Fissi: modello **gpt-4o-mini** su tutti gli agenti, persona neutra (stesso preset),
3 reviewer, max_rounds=1, temperature 0.4, top_k=5, max_tool_iterations=3.

| config | context_mode reviewer | tool |
|---|---|---|
| `full` | full_context | no |
| `summary` | summary | no |
| `summary+tool` | summary | sì |
| `tool-only` | none | sì |

Meta-reviewer / area chair / autore: sempre `none`, senza tool.

Volume: 10 paper × 4 config × 3 rep = **120 run** (~1-2 $ stimati con gpt-4o-mini).
Nota: il summary si paga una volta per paper (cache) — generarlo col primo run.

## RQ2 — Modello

*Frontiera qualità/costo.* Fissi: la config vincente di RQ1 + `full` come controllo,
stessa persona neutra. Si varia il modello dei reviewer (e del summarizer, coerente):

| config | modello |
|---|---|
| `4o-mini` | gpt-4o-mini (già dai run RQ1) |
| `4o` | gpt-4o |
| `local` | mistral:7b via Ollama (richiede fix num_ctx ≥ 16k) |
| (opz.) `haiku` | claude-haiku |

Volume: 5 paper (sottoinsieme bilanciato 3+2) × 2 config di contesto × 3 rep per
ogni modello nuovo. gpt-4o è la voce di costo dominante: ~30 run ≈ 2-3 $.

## RQ3 — Comitato e persona

*La composizione del comitato cambia l'esito?* Fissi: modello ed eventuale contesto
vincenti (economici, es. 4o-mini + summary+tool). Si varia il comitato:

| config | comitato (3 reviewer) |
|---|---|
| `neutral` | 3 × preset neutro (già dai run precedenti) |
| `hetero` | severo + focus-novelty + focus-soundness |
| `strict` | 3 × severo |

Volume: 10 paper × 2 config nuove × 3 rep = 60 run.

## Test supplementari

**S1 — Stabilità/ripetibilità.** Stessa configurazione (la vincente di RQ1) ripetuta
10 volte su 2-3 paper: varianza dei rating e della decisione. Risponde a "se lo
rilanci, dice la stessa cosa?". ~30 run.

**S2 — Qualità del summarizer.** Config `summary` con riassunto generato da
gpt-4o-mini vs da gpt-4o, reviewer invariato: isola quanto pesa la qualità del
riassunto rispetto al reviewer. Attenzione: cambiare `SUMMARIZER_MODEL` solo tra
i due blocchi, mai dentro. ~30 run.

**S3 — Dinamica del rebuttal** *(richiede prima il fix del flusso round 2)*.
max_rounds=2 vs 1 sulla config vincente: la decisione cambia dopo il rebuttal?
~60 run.

Fuori scope dichiarato: sensibilità a top_k/iterazioni/temperature, bm25 vs
embedding (embedder mock), valutazione testuale LLM-as-judge (sviluppo futuro).

## Metriche

| Gruppo | Metrica | Dove si legge |
|---|---|---|
| Allineamento | match decisione; Δ rating medio; Δ confidence; Δ sub-score | comparator (per run) |
| Operative | token in/out per run e per agente; latenza; costo € (token × listino) | dettagli run / Postgres |
| Comportamentali (config con tool) | n° tool call per review, query emesse | tool_trace nei dettagli tecnici |
| Dispersione (RQ3) | spread dei rating tra reviewer, cambi di decisione vs `neutral` | confronto tra run |

Aggregazione: media ± deviazione standard sulle 3 ripetizioni, poi media sui paper,
tenendo separati accettati e rifiutati (l'allineamento sui rifiutati è spesso
la parte interessante).

## Prerequisiti tecnici ancora aperti

- [ ] Listino prezzi per modello → costo € per run (roadmap README).
- [ ] Fix `num_ctx` Ollama (solo se si fa la config `local` in RQ2).
- [ ] Chiavi API (OpenAI per RQ1; Anthropic opzionale per RQ2).

## Scaletta operativa

**A — Preparazione tecnica (una tantum)**
1. Commit dello stato attuale del repo (feature RAG + README + questo piano): baseline pulita e riproducibile.
2. Listino prezzi per modello (config `model_pricing` + costo € per run derivato dai token già registrati).
3. *(solo se RQ2 includerà Ollama)* fix `num_ctx` nel builder Ollama.
4. Giro end-to-end mock con l'app viva: upload → review → storico → comparator, tutto funziona.

**B — Dataset**
5. Selezionare i 10 paper su openreview.net (ICLR 2026, 5+5, piccoli, review complete); annotare le date arXiv.
6. Caricarli col loader OpenReview e compilare la tabella paper_id → tag p01..p10 con esito e rating medio umano.
7. Verificare nel comparator il parsing delle review umane di ogni paper; verificare in Redis la dimensione del full_context (< ~40k char).

**C — Configurazione**
8. I preset della campagna sono **seedati dal codice** al primo avvio (`preset_default.py`): reviewer `exp_neutral` / `exp_strict` / `exp_focus_novelty` / `exp_focus_soundness`, più `exp_default` per meta-reviewer, area chair e autore (tutti su base ML-conference, venue ICLR dove pertinente). Verificarli nella sezione Prompt della UI e annotare gli id assegnati. Non modificarli a campagna in corso.
9. Preparare e provare le 4 configurazioni del grafo di RQ1 (salvate dalla UI), con la convenzione di etichetta pronta.

**D — Collaudo (mock, gratis)**
10. Run `RQ0|...` per ogni config su 2-3 paper. Checklist di uscita: summary generato e cachato, tool_trace nei dettagli tecnici, token registrati, comparator che aggrega.

**E — Campagna reale**
11. Chiave OpenAI in `.env`; 1 run reale di smoke su 1 paper: output strutturato ok, costi/latenze plausibili.
12. **RQ1**: 120 run etichettati (procedere per paper: il primo run genera il summary, gli altri lo riusano).
13. Analisi intermedia RQ1 → scelta della config vincente (serve per RQ2/RQ3).
14. **RQ2** sui 5 paper del sottoinsieme; **RQ3** sui 10.
15. **S1** e **S2** quando comodo (indipendenti); *(opz.)* fix round 2 → **S3**.

**F — Analisi e scrittura**
16. Estrazione dei dati (query su `graph_review`/`graph_review_agent` via Adminer, o export) → tabelle e grafici per RQ.
17. Scrittura del capitolo Risultati; sostituzione dei risultati segnaposto nell'abstract della tesi.

## Note operative

- Prima di ogni sessione di run: stesso preset di prompt per tutti (annotare
  versione/preset id usato — cambia il prompt, cambiano i risultati).
- Non modificare i file dei paper a campagna iniziata (la firma-file invalida
  gli indici e il summary verrebbe rigenerato, potenzialmente diverso).
- Se si cambia `SUMMARIZER_MODEL` a metà campagna i summary vengono rigenerati
  col nuovo modello (doc_id diverso): va bene solo tra una RQ e l'altra, mai
  dentro la stessa.
