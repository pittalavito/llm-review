# Thesis artifacts

This folder hosts the artifacts that link the repository to the thesis
*"Simulazione della peer review con agenti LLM: progettazione e valutazione
sperimentale di un'applicazione web"* (University of Catania).

Planned contents (populated at submission time):

| File | Description |
|---|---|
| `tesi_frozen.pdf` | The exact thesis version submitted for review — the same PDF that was loaded into the application and reviewed by the artificial committee. |
| `app_review_run.json` | Full record of that review run, exported from `/graph/runs/{run_id}`: reviews, meta-review, decision, composed prompts and traces. |
| `confronto_relatore.md` | Comparison between the application's review and the human supervisor's remarks (added after the supervision cycle). |

## Why

The thesis validates the system by comparing artificial reviews with human
ones on papers with known outcomes. As a closing experiment, the same method
is applied to the thesis itself: the application reviews the document that
describes it (with thesis-adapted prompts — not the ICLR ones), and the
result is compared with the supervisor's actual review of the same frozen
version. The outcome lives here, next to the code that produced it.
