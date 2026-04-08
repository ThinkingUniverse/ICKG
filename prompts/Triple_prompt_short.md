# Biomedical Knowledge Triple Extraction

You are a biomedical NLP specialist. Extract structured knowledge triples from PubMed abstracts for immunology knowledge graph construction.

## Triple Format
**(head_entity [entity_type], relation, tail_entity [entity_type])**

## Entity Types
| Type | Description & Examples |
|---|---|
| `disease` | Pathological conditions (rheumatoid arthritis, COVID-19) |
| `phenotype` | Observable biological/clinical characteristics (lymphopenia, CD4/CD8 ratio) |
| `chemical` | Non-drug substances: metabolites, toxins, signaling molecules (ROS, LPS) |
| `cell_type` | Immune/non-immune cell types and subtypes (CD8+ T cell, pDC) |
| `species` | Organisms (Homo sapiens, Mus musculus, microorganism) |
| `method` | Experimental/analytical techniques (flow cytometry, scRNA-seq, ELISA) |
| `physiology` | Normal biological processes (immune homeostasis, cell proliferation) |
| `pathology` | Abnormal biological processes (chronic inflammation, fibrosis) |
| `protein` | Cytokines, receptors, enzymes, transcription factors (IL-6, PD-1, NFκB) |
| `anatomy` | Tissues, organs, compartments (lymph node, bone marrow, TME) |
| `gene` | Genes or genetic loci (FOXP3, TNF, HLA-DR) |
| `intervention` | Deliberate therapeutic/preventive actions: drugs, surgery, diet, exercise, vaccination (pembrolizumab, aerobic exercise, Mediterranean diet) |
| `time` | Temporal references (12 weeks, acute phase, early onset) |
| `health_factors` | Lifestyle/environmental/demographic factors (smoking, obesity, aging, sex) |
| `pathway` | Molecular/signaling pathways (JAK-STAT, NF-κB signaling) |
| `relationship` | A named inter-entity association, typically as object of `mediates` (e.g., association between gut microbiome and immune activation) |

> **Boundary notes:** `intervention` = deliberately applied agent/action; `chemical` = substance in biological context without therapeutic framing. `physiology` = normal; `pathology` = abnormal. `relationship` = when an association itself is referenced as a concept.

## Relation Types (all directional: head → relation → tail)
| Relation | Meaning |
|---|---|
| `associated_with` | Association exists but directionality/mechanism unclear, or non-committal language used. Use only when no more specific relation applies. |
| `results_in` | Direct causation (strong) |
| `promotes` | Facilitates/drives (moderate, not necessarily direct) |
| `activates` | Molecular/cellular activation |
| `inhibits` | Molecular/cellular suppression/blocking |
| `increases` | Quantitative upregulation/elevation |
| `decreases` | Quantitative downregulation/reduction |
| `exacerbates` | Worsens/aggravates |
| `improves` | Ameliorates symptoms, biomarkers, or outcomes |
| `increases_risk_of` | Risk factor elevating probability of B |
| `co-occurs_with` | Frequent co-occurrence or comorbidity (symmetric) |
| `treatment_for` | Intervention A used to treat disease/condition B |
| `mediates` | A is intermediary through which upstream cause leads to B |
| `positively_correlated_with` | Statistical positive correlation (no causal implication) |
| `negatively_correlated_with` | Statistical negative correlation (no causal implication) |
| `u_shaped_association_with` | Non-monotonic U-shaped association |
| `inverted_u_shaped_association_with` | Inverted U-shaped association |
| `includes` | A contains B as component or subtype |
| `hyponym_of` | A is a subtype/instance of B |
| `abbreviation_for` | A is abbreviation/acronym for B |
| `characteristic_of` | A is a feature/characteristic of B |
| `help_identify` | A can identify/detect B |
| `secretes` | Cell type A secretes protein/chemical B |
| `expressed_by` | Gene/protein A is expressed by cell type B |
| `binds_to` | Physical binding (receptor-ligand, antibody-antigen) |
| `differentiates_into` | Cell type A differentiates into cell type B |
| `marker_for` | A serves as phenotypic marker to identify B |
| `located_in` | A is found in anatomical location B |

## Output Format
Return a **JSON array** only — no explanatory text outside it. Empty input → `[]`.

```json
[
  {
    "head": "entity name",
    "head_type": "entity_type",
    "relation": "relation_type",
    "tail": "entity name",
    "tail_type": "entity_type",
    "source_sentence": "verbatim sentence from abstract",
    "score": 95
  }
]
```

**Field rules:**
- `source_sentence`: verbatim minimal clause supporting the triple; for cross-sentence inferences, use the most directly relevant sentence
- `score`: confidence 0–100 — explicitly stated & unambiguous (90–100); single-step inference (70–89); multi-step inference (50–69); plausible but uncertain (30–49); background knowledge, weak support (<30)
- Normalize entity names to standard nomenclature (IL-6 not interleukin 6; T cell not T lymphocyte)

## Extraction Rules
- Extract explicitly stated triples (score 90–100); single-step (70–89) and multi-step (50–69) inferences permitted; speculative triples allowed at score <50
- Extract nested relations independently: if A→B and B→C, extract both triples
- Assign the most specific applicable relation type; use `associated_with` only when no more specific type fits
- Deduplicate: retain the most specific version of near-identical triples
- Validate: both entity types and relation must be from predefined lists; direction must match text

Think step by step.

## Input
{Unraveling the immunological landscape and gut microbiome in sepsis: a comprehensive approach to diagnosis and prognosis. Background Comprehensive and in-depth research on the immunophenotype of septic patients remains limited, and effective biomarkers for the diagnosis and treatment of sepsis are urgently needed in clinical practice. Methods Blood samples from 31 septic patients in the Intensive Care Unit (ICU), 25 non-septic ICU patients, and 18 healthy controls were analyzed using flow cytometry for deep immunophenotyping. Metagenomic sequencing was performed in 41 fecal samples, including 13 septic patients, 10 non-septic ICU patients, and 18 healthy controls. Immunophenotype shifts were evaluated using differential expression sliding window analysis, and random forest models were developed for sepsis diagnosis or prognosis prediction. Findings Septic patients exhibited decreased proportions of natural killer (NK) cells and plasmacytoid dendritic cells (pDCs) in CD45+ leukocytes compared with non-septic ICU patients and healthy controls. These changes statistically mediated the association of Bacteroides salyersiae with sepsis, suggesting a potential underlying mechanism. A combined diagnostic model incorporating B.salyersia, NK cells in CD45+ leukocytes, and C-reactive protein (CRP) demonstrated high accuracy in distinguishing sepsis from non-sepsis (area under the receiver operating characteristic curve, AUC = 0.950, 95% CI: 0.811–1.000). Immunophenotyping and disease severity analysis identified an Acute Physiology and Chronic Health Evaluation (APACHE) II score threshold of 21, effectively distinguishing mild (n = 19) from severe (n = 12) sepsis. A prognostic model based on the proportion of total lymphocytes, Helper T (Th) 17 cells, CD4+ effector memory T (TEM) cells, and Th1 cells in CD45+ leukocytes achieved robust outcome prediction (AUC = 0.906, 95% CI: 0.732–1.000), with further accuracy improvement when combined with clinical scores (AUC = 0.938, 95% CI: 0.796–1.000). Interpretation NK cell subsets within innate immunity exhibit significant diagnostic value for sepsis, particularly when combined with B. salyersiae and CRP. In addition, T cell phenotypes within adaptive immunity are correlated with sepsis severity and may serve as reliable prognostic markers.}