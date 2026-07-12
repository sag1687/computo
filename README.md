# Computo Metrico GIS

[![QGIS](https://img.shields.io/badge/QGIS-3.22%2B%20%7C%204.x-589632?logo=qgis&logoColor=white)](https://qgis.org/)
[![License](https://img.shields.io/badge/license-GPL--2.0-blue)](metadata.txt)
[![Version](https://img.shields.io/badge/version-0.3.1-informational)](metadata.txt)
[![Status](https://img.shields.io/badge/status-experimental-orange)](metadata.txt)

Plugin QGIS per **computo metrico estimativo** e **contabilità lavori** basati su layer vettoriali, prezziari regionali italiani o file `CSV` / `XLSX` / `DCF` leggibili, con archivio `SQLite`, `SAL`, giornale lavori, report `PDF` / `XLSX` e progetto demo.

QGIS plugin for **bill of quantities** and **works accounting** based on vector layers, Italian regional price lists or readable `CSV` / `XLSX` / `DCF` files, with a local `SQLite` archive, progress payments (`SAL`), works journal, `PDF` / `XLSX` reports and a demo project.

## Premesse Importanti / Important Notice

- `IT:` Questo plugin e' **sperimentale**. I risultati vanno sempre verificati da un tecnico abilitato prima di uso contrattuale, contabile o esecutivo.
- `EN:` This plugin is **experimental**. Results must always be checked by a qualified professional before contractual, accounting or construction use.
- `IT:` Il plugin aiuta a strutturare i dati, misurare le geometrie e produrre report. Non sostituisce direzione lavori, contabilita ufficiale o verifica normativa.
- `EN:` The plugin helps structure data, measure geometries and produce reports. It does not replace works supervision, official accounting or regulatory review.
- `IT:` Per risultati metrici affidabili usa un **CRS proiettato metrico** coerente con l'area di lavoro.
- `EN:` For reliable measurements use a **projected metric CRS** consistent with your work area.

## Funzionalita Principali / Main Features

- `IT:` Database `SQLite` locale inizializzato dal plugin per profili documento, prezziari, run di computo e contabilita.
- `EN:` Local `SQLite` database managed by the plugin for document profiles, price lists, computation runs and accounting.
- `IT:` Import prezziari da `CSV`, `XLSX`, `XLSM`, `ZIP` con file compatibili interni e `DCF` solo quando il contenitore e' realmente leggibile.
- `EN:` Price list import from `CSV`, `XLSX`, `XLSM`, `ZIP` archives with compatible internal files, and `DCF` only when the container is actually readable.
- `IT:` Catalogo regionale con fonti ufficiali, stato del dataset e download locale del file trovato sul portale.
- `EN:` Regional catalog with official sources, dataset status and local download of the file discovered on the official portal.
- `IT:` Dataset bundled gia' pronto quando disponibile, ad esempio `data/bundled/basilicata_2026_lavorazioni.csv`.
- `EN:` Bundled ready-to-use datasets when available, for example `data/bundled/basilicata_2026_lavorazioni.csv`.
- `IT:` Template manuale regionale per i casi in cui il portale ufficiale non espone ancora un formato importabile con affidabilita.
- `EN:` Manual regional template for cases where the official portal does not yet expose a reliably importable format.
- `IT:` Calcolo quantita da punti, linee e poligoni, con override manuale, coefficienti e campi dimensionali opzionali.
- `EN:` Quantity computation from points, lines and polygons, with manual overrides, coefficients and optional dimensional fields.
- `IT:` Scheda `Contabilita` con libretto misure, registro, sommario per categoria, `SAL`, certificato di pagamento e giornale lavori.
- `EN:` `Accounting` tab with measurement book, ledger, category summary, `SAL`, payment certificate and works journal.
- `IT:` Report `PDF` e workbook `XLSX` con logo, titolo, riferimenti, riepilogo, dettaglio e mappa corrente del progetto.
- `EN:` `PDF` reports and `XLSX` workbooks with logo, title, references, summary, detail tables and the current project map.
- `IT:` Progetto demo completo con layer, prezziario e output iniziali per vedere subito il flusso corretto.
- `EN:` Complete demo project with layers, price list and starter outputs so the expected workflow is visible immediately.

## Schede Del Plugin / Plugin Tabs

| Scheda / Tab | Scopo / Purpose |
| --- | --- |
| `Info` | Panoramica del plugin, stato locale, accesso rapido al progetto demo. |
| `Prezziari` | Sorgenti ufficiali, download, archivio prezziari, import file, attivazione listino. |
| `Misurazioni` | Selezione layer e mapping dei campi per il calcolo del computo. |
| `Computo` | Profilo documento, riepilogo, dettaglio, esportazioni `PDF` / `XLSX`. |
| `Contabilita` | Libretto, registro, sommario, `SAL`, certificati e giornale lavori. |
| `Help` | Istruzioni operative e formato atteso di layer e prezziari. |

## Flusso Operativo Consigliato / Recommended Workflow

1. `IT:` Avvia il plugin e lascia che inizializzi il database locale.
   `EN:` Start the plugin and let it initialize the local database.
2. `IT:` Se vuoi un esempio funzionante subito, crea il progetto demo dalla scheda `Info`.
   `EN:` If you want a working example immediately, create the demo project from the `Info` tab.
3. `IT:` Vai in `Prezziari` e usa prima il catalogo regionale: capisci subito se il dataset e' bundled, scaricabile o solo manuale.
   `EN:` Go to `Price lists` and start from the regional catalog: you immediately see whether the dataset is bundled, downloadable or manual-only.
4. `IT:` Importa un dataset incluso, un file `CSV` / `XLSX`, uno `ZIP` compatibile o un `DCF` leggibile.
   `EN:` Import a bundled dataset, a `CSV` / `XLSX` file, a compatible `ZIP` archive or a readable `DCF`.
5. `IT:` Seleziona il layer di lavoro in `Misurazioni`, controlla il mapping dei campi e calcola il computo.
   `EN:` Select the working layer in `Measurements`, review the field mapping and compute the bill of quantities.
6. `IT:` Completa profilo documento, riferimenti e mappa in `Computo`, poi esporta `PDF` e `XLSX`.
   `EN:` Complete the document profile, references and map in `Reports`, then export `PDF` and `XLSX`.
7. `IT:` Usa `Contabilita` per emettere `SAL`, certificati di pagamento e giornale lavori.
   `EN:` Use `Accounting` to issue `SAL`, payment certificates and the works journal.

## Formato Minimo Prezziario / Minimum Price List Format

```csv
codice;descrizione;um;prezzo_unitario;categoria;note
DEM-AREA-001;Pavimentazione drenante;mq;36,20;Superfici;Area da geometria
```

Alias riconosciuti / Recognized aliases:

- `code`: `codice`, `code`, `item_code`, `voce`, `cod`
- `description`: `descrizione`, `description`, `articolo`, `desc`
- `unit`: `um`, `unita`, `unit`, `u_m`
- `unit_price`: `prezzo`, `prezzo_unitario`, `unit_price`, `price`, `totale_generale`
- `category`: `categoria`, `category`, `capitolo`, `gruppo`, `tipologia`
- `notes`: `note`, `notes`, `osservazioni`

Note operative / Operational notes:

- `IT:` I decimali `36,20` e `36.20` sono entrambi accettati.
- `EN:` Both `36,20` and `36.20` decimal formats are accepted.
- `IT:` Il separatore `CSV` puo' essere `;` oppure `,`.
- `EN:` The `CSV` delimiter may be either `;` or `,`.
- `IT:` Il supporto `DCF` e' prudente: il file viene accettato solo se leggibile come `ZIP`, `SQLite` o tabella uniforme.
- `EN:` `DCF` support is intentionally conservative: the file is accepted only when it is readable as `ZIP`, `SQLite` or a uniform table.

## Campi Consigliati Del Layer / Recommended Layer Fields

| Campo / Field | Richiesto / Required | Uso / Purpose |
| --- | --- | --- |
| `item_code` | Si / Yes | Codice voce del prezziario attivo. |
| `descrizione` | No | Descrizione specifica della feature. |
| `categoria` | No | Raggruppamento o capitolo. |
| `quantita_man` | No | Override manuale della quantita. |
| `coefficiente` | No | Moltiplicatore numerico della quantita finale. |
| `unita_override` | No | Forza l'unita di misura della feature. |
| `larghezza_m` | No | Superfici da linee, volumi da elementi lineari. |
| `altezza_m` | No | Volumi da linee o punti. |
| `spessore_m` | No | Volumi da poligoni o linee. |
| `pezzi` | No | Quantita a corpo o conteggio personalizzato. |
| `note` | No | Annotazioni riportate nei report. |

Regole di misura automatiche / Automatic measurement rules:

- `mq` / `ha`: area geometrica.
- `ml` / `km`: lunghezza; per i poligoni puo' usare il perimetro.
- `cad`: una unita per feature, oppure il valore di `pezzi`.
- `mc`: `area x spessore` oppure `lunghezza x larghezza x altezza/spessore`.

## Catalogo Regionale / Regional Catalog

Il catalogo distingue tre stati principali / The catalog distinguishes three main states:

- `Dataset pronto / Bundled dataset`: il plugin include gia' un file normalizzato e importabile.
- `Conversione manuale / Manual conversion`: la fonte ufficiale esiste ma non e' ancora affidabile per import diretto.
- `Portale censito / Portal indexed`: la regione e' nota, ma il dataset non e' ancora bundle locale.

Quando il download automatico trova un file, questo viene salvato localmente in una cartella del plugin o del progetto per poter essere controllato e riutilizzato manualmente.

When automatic download finds a file, it is saved locally in a plugin or project folder so it can be inspected and reused manually.

## Output Prodotti / Produced Outputs

- `IT:` Run di computo salvati nel database locale con riepilogo e dettaglio.
- `EN:` Computation runs stored in the local database with summary and detail rows.
- `IT:` Report `PDF` con logo, titolo, riferimenti, tabella riepilogo, dettaglio e mappa corrente opzionale.
- `EN:` `PDF` report with logo, title, references, summary table, detail rows and optional current map.
- `IT:` Workbook `XLSX` con fogli strutturati per riepilogo, dettaglio e riferimenti.
- `EN:` `XLSX` workbook with structured sheets for summary, detail and references.
- `IT:` File scaricati dai portali regionali e template manuali da completare.
- `EN:` Downloaded files from regional portals and manual templates ready to be completed.
- `IT:` Progetto demo `QGIS` con layer e prezziario dimostrativi.
- `EN:` Demo `QGIS` project with example layers and price list.

## Sicurezza E Limiti / Security And Limits

- `IT:` I download remoti accettano solo URL `http` / `https`; altri schemi vengono rifiutati.
- `EN:` Remote downloads accept only `http` / `https` URLs; other schemes are rejected.
- `IT:` La verifica `TLS` dei certificati e' attiva di default nei download dei prezziari.
- `EN:` `TLS` certificate verification is enabled by default for price list downloads.
- `IT:` Il parsing `XML` dei file `XLSX` rifiuta `DTD` ed entita', per mitigare payload malevoli.
- `EN:` `XML` parsing for `XLSX` files rejects `DTD` declarations and entities to mitigate malicious payloads.
- `IT:` Se un codice voce non esiste nel prezziario attivo, il plugin lo segnala e non inventa valori.
- `EN:` If an item code does not exist in the active price list, the plugin reports it and does not invent values.
- `IT:` Per file ufficiali pubblicati solo in `PDF`, il plugin puo' scaricare il documento ma non forza un'importazione ambigua.
- `EN:` For official sources published only as `PDF`, the plugin can download the document but does not force an ambiguous import.

## Installazione / Installation

1. Copia la cartella `COMPUTO` nella directory dei plugin di QGIS.
2. Riavvia QGIS oppure aggiorna l'elenco plugin.
3. Attiva `Computo Metrico GIS` dal gestore plugin.

1. Copy the `COMPUTO` folder into the QGIS plugins directory.
2. Restart QGIS or refresh the plugin list.
3. Enable `Computo Metrico GIS` from the plugin manager.

## Verifiche Locali / Local Verification

- `IT:` Suite `pytest` locale: `12 passed`.
- `EN:` Local `pytest` suite: `12 passed`.
- `IT:` `ruff check` sul plugin: ok.
- `EN:` `ruff check` on the plugin: ok.

Nota / Note:

- `IT:` Un `flake8` con limite rigido `79` caratteri segnala ancora molte `E501`; non e' un errore funzionale ma una scelta di stile residua.
- `EN:` A strict `flake8` run with `79`-character lines still reports many `E501` entries; this is a residual style choice, not a functional defect.

## Repository E Autore / Repository And Author

- Pagina autore QGIS / QGIS author page: <https://plugins.qgis.org/plugins/author/Dott.%20Sarino%20Alfonso%20Grande/>
- GitHub: <https://github.com/sag1687>
- Email: <info@sinocloud.it>
