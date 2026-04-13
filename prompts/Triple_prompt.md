# Biomedical Knowledge Triple Extraction Prompt

## Role and Task

You are an expert biomedical NLP specialist focused on constructing knowledge graphs from immunology literature.
Your task is to extract structured knowledge triples from PubMed abstracts.

---

## Triple Format

A knowledge triple consists of: **(head_entity [entity_type], relation, tail_entity [entity_type])**

All entities must be assigned one of the predefined entity types.
All relations must be one of the predefined relation types.

---

## Predefined Entity Types

| Entity Type | Description |
|---|---|
| `disease` | Pathological conditions or disorders (e.g., rheumatoid arthritis, COVID-19) |
| `phenotype` | Observable biological characteristics or clinical presentations (e.g., lymphopenia, Treg cells in T cells, proportion of NK cells, higher proportion of monocytes, CD4/CD8 T cell ratio, morphology of T cells, CD40 on B cells) |
| `chemical` | Non-drug chemical substances including metabolites, toxins, signaling molecules (e.g., reactive oxygen species, LPS) |
| `cell_type` | Immune or non-immune cell types and subtypes (e.g., CD8+ T cell, plasmacytoid dendritic cell) |
| `species` | Any organism species, including animals, plants, microorganisms, and all other living taxa (e.g., Homo sapiens, Mus musculus, Arabidopsis thaliana, Escherichia coli, SARS-CoV-2) |
| `method` | Experimental or analytical techniques (e.g., flow cytometry, scRNA-seq, ELISA) |
| `physiology` | Normal biological processes or states (e.g., immune homeostasis, cell proliferation) |
| `pathology` | Abnormal biological processes or states (e.g., chronic inflammation, fibrosis) |
| `protein` | Proteins, including cytokines, receptors, enzymes, and transcription factors (e.g., IL-6, PD-1, NFκB) |
| `anatomy` | Anatomical locations including tissues, organs, and body compartments (e.g., lymph node, bone marrow, tumor microenvironment) |
| `gene` | Genes or genetic loci (e.g., FOXP3, TNF, HLA-DR) |
| `variant` | Genetic variants, mutations, polymorphisms, or isoforms (e.g., rs1234567, BRCA1 V600E, splice variant, missense mutation) |
| `intervention` | Any deliberate action or agent applied to modify health or biological outcomes, including pharmacological agents, surgical procedures, dietary regimens, physical exercise, supplementation, behavioral programs, and other therapeutic or preventive measures (e.g., pembrolizumab, methotrexate, aerobic exercise, Mediterranean diet, caloric restriction, vaccination, cognitive behavioral therapy) |
| `time` | Temporal references (e.g., 12 weeks, acute phase, early onset) |
| `health_factors` | Lifestyle, environmental, or demographic factors (e.g., smoking, obesity, aging, sex) |
| `pathway` | Molecular or signaling pathways (e.g., JAK-STAT pathway, NF-κB signaling) |
| `relationship` | A documented association or link between two other entities, typically used as the tail of a `mediates` triple (e.g., association between Bacteroides salyersiae and sepsis, link between gut microbiome and immune activation) |

> **Boundary notes:**
> - Use `intervention` for any deliberate therapeutic or preventive action; use `chemical` for substances that appear in a biological context without being framed as an applied intervention.
> - Use `physiology` for normal processes; use `pathology` for abnormal or disease-associated processes.
> - Use `relationship` when the text refers to an inter-entity association as a named concept in itself — most commonly as the object of a mediation statement (e.g., "X mediates the association between A and B" → extract: (X, `mediates`, association between A and B [`relationship`])).

---

## Predefined Relation Types

All relations are **directional**: (head_entity → relation → tail_entity).

| Relation | Direction & Meaning |
|---|---|
| `associated_with` | A is statistically, clinically, or biologically associated with B — use when the relationship is either real or implied but its directionality or mechanistic nature cannot be determined from the text, or when the text uses neutral or non-committal language (e.g., "associated with", "linked to", "related to", "involved in"). **This relation also subsumes the following verbs when they do not imply a clear mechanism or direction: *regulates, participates in, affects, influences, modulates, changes*.** Do **not** use when a more specific relation type clearly applies. |
| `results_in` | A directly causes or leads to B (strong causation) |
| `promotes` | A facilitates or drives B (moderate causation, not necessarily direct) |
| `activates` | A activates B (specific to molecular/cellular activation events) |
| `inhibits` | A suppresses or blocks B (specific to molecular/cellular inhibition) |
| `increases` | A quantitatively upregulates or elevates B |
| `decreases` | A quantitatively downregulates or reduces B |
| `exacerbates` | A worsens or aggravates B |
| `improves` | A ameliorates or alleviates B (symptoms, biomarkers, or outcomes — not used for therapeutic indication) |
| `increases_risk_of` | A is a risk factor that elevates the probability of B occurring |
| `co-occurs_with` | A and B frequently co-occur, are comorbid, or are co-expressed |
| `treatment_for` | A (`intervention`) is used as a treatment or management strategy for disease or condition B |
| `prevents` | A reduces or eliminates the occurrence or development of B (e.g., vaccination prevents infection) |
| `targets` | A specifically acts on or is directed against B as its primary molecular or cellular target (e.g., pembrolizumab targets PD-1) |
| `mediates` | A acts as an intermediary through which an upstream cause leads to B |
| `positively_correlated_with` | A and B are statistically positively correlated (no causal implication) |
| `negatively_correlated_with` | A and B are statistically negatively correlated (no causal implication) |
| `u_shaped_association_with` | A has a U-shaped (non-monotonic) association with B |
| `inverted_u_shaped_association_with` | A has an inverted U-shaped association with B |
| `includes` | A contains or encompasses B as a component or subtype |
| `hyponym_of` | A is a subtype, specific instance, component, or derivative of B. **This relation subsumes *derived_from*, *part_of*, and *subset_of***: use `hyponym_of` when A is derived from B, is a part of B, or is a subset of B, in addition to the standard subtype/instance sense. |
| `abbreviation_for` | A is an abbreviation or acronym for B |
| `help_identify` | A can be used to identify, detect, predict, measure, serve as a marker for, or is a characteristic of B. **This relation subsumes *predicts*, *measures*, *marker for*, and *characteristic of***: use when A is a tool, method, biomarker, surface marker, or feature that characterizes, distinguishes, quantifies, or typifies B. |
| `secretes` | Cell type A secretes protein/chemical B |
| `expresses` | Cell type, tissue, or organ A (`cell_type` or `anatomy`) expresses gene or protein B (`gene` or `protein`) |
| `binds_to` | A physically binds to B (receptor-ligand, antibody-antigen) |
| `differentiates_into` | Cell type A differentiates into cell type B |
| `located_in` | A is found in or anatomically situated within anatomy B |

---

## Output Format

Return a **JSON array** of triples. Each triple is a JSON object with the following fields:
```json
[
  {
    "head": "CD8+ T cell",
    "head_type": "cell_type",
    "relation": "secretes",
    "tail": "IFN-γ",
    "tail_type": "protein",
    "source_sentence": "CD8+ T cells were shown to secrete IFN-γ upon activation.",
    "score": 100
  },
  {
    "head": "IFN-γ",
    "head_type": "protein",
    "relation": "activates",
    "tail": "macrophage",
    "tail_type": "cell_type",
    "source_sentence": "IFN-γ activated macrophages to enhance their phagocytic activity.",
    "score": 100
  }
]
```

- `source_sentence`: the single sentence (or minimal clause) from the input abstract that most directly supports the triple. Copy it verbatim from the source text. For triples derived by inference across adjacent sentences, include the most directly relevant sentence.
- `score`: an integer from 0 to 100 reflecting your confidence that this triple is correctly extracted — considering accuracy of entity typing, relation selection, directionality, and how well the source sentence supports the triple. Score 90–100 for explicitly stated triples with unambiguous typing; 70–89 for implied single-step inferences; 50–69 for implied multi-step inferences; 30–49 for plausible but less certain inferences; below 30 for triples that rely on background knowledge and weak textual support.
- Normalize entity names: use standard nomenclature (e.g., "IL-6" not "interleukin 6", "T cell" not "T lymphocyte")
- Do not include explanatory text outside the JSON array
- If the text contains no extractable triples, return an empty array: `[]`

---

## Extraction Rules

**Scope — text-grounded extraction with inference permitted:**
Prioritize relationships that are directly and explicitly stated in the source text (typically scoring 90–100). You may also apply reasoning grounded in the text — including single-step (70–89) and multi-step (50–69) inferences — to extract triples that are plausibly supported by the content. Less certain and weakly supported inferences may be included with moderate confidence (30–49). Triples that rely primarily on background knowledge and have minimal textual support are permitted but should receive a low `score` (below 30). Use the `score` field to transparently communicate your confidence in each extracted triple; do not suppress uncertain triples, but assign scores that accurately reflect their level of support.


**Entity extraction:**
Identify mentions of diseases, phenotypes, chemicals, cell types, species, methods, physiological processes, pathological processes, proteins, anatomical locations, genes, variants, interventions, temporal references, health factors, pathways, and relationships. Assign each identified mention the most specific matching entity type from the predefined list.

**Relation assignment:**
For each entity pair where the text states or implies a relationship, assign the most specific and accurate relation type from the predefined list.
Prefer `associated_with` over leaving a real or implied relationship unextracted.
The verb 'induces' should be mapped to `results_in`, `promotes`, or `activates` depending on whether the causal relationship is direct, facilitative, or activation-specific.

**Nested relations:**
If entity A relates to B, and B relates to C, extract both (A, relation, B) and (B, relation, C) as independent triples.

**Validation:**
Confirm that: (a) both entities have valid predefined types, (b) the relation is from the predefined list, and (c) the direction is consistent with the text.

**Deduplication:**
Remove semantically identical triples. If near-duplicates exist, retain the most specific version.

Let's think step by step.

---

## Example

**Input abstract (excerpt):**
*"In patients with rheumatoid arthritis (RA), circulating monocytes are elevated and secrete high levels of TNF-α, which activates synovial fibroblasts and contributes to joint inflammation. Anti-TNF therapy significantly reduced RA disease activity scores."*

**Output:**
```json
[
  {
    "head": "RA",
    "head_type": "disease",
    "relation": "abbreviation_for",
    "tail": "rheumatoid arthritis",
    "tail_type": "disease",
    "source_sentence": "In patients with rheumatoid arthritis (RA)",
    "score": 100
  },
  {
    "head": "rheumatoid arthritis",
    "head_type": "disease",
    "relation": "increases",
    "tail": "monocyte",
    "tail_type": "cell_type",
    "source_sentence": "In patients with rheumatoid arthritis (RA), circulating monocytes are elevated and secrete high levels of TNF-α",
    "score": 89
  },
  {
    "head": "monocyte",
    "head_type": "cell_type",
    "relation": "secretes",
    "tail": "TNF-α",
    "tail_type": "protein",
    "source_sentence": "circulating monocytes are elevated and secrete high levels of TNF-α",
    "score": 100
  },
  {
    "head": "TNF-α",
    "head_type": "protein",
    "relation": "activates",
    "tail": "synovial fibroblast",
    "tail_type": "cell_type",
    "source_sentence": "circulating monocytes are elevated and secrete high levels of TNF-α, which activates synovial fibroblasts and contributes to joint inflammation",
    "score": 92
  },
  {
    "head": "TNF-α",
    "head_type": "protein",
    "relation": "promotes",
    "tail": "joint inflammation",
    "tail_type": "pathology",
    "source_sentence": "circulating monocytes are elevated and secrete high levels of TNF-α, which activates synovial fibroblasts and contributes to joint inflammation",
    "score": 92
  },
  {
    "head": "anti-TNF therapy",
    "head_type": "intervention",
    "relation": "treatment_for",
    "tail": "rheumatoid arthritis",
    "tail_type": "disease",
    "source_sentence": "Anti-TNF therapy significantly reduced RA disease activity scores.",
    "score": 94
  },
  {
    "head": "anti-TNF therapy",
    "head_type": "intervention",
    "relation": "decreases",
    "tail": "rheumatoid arthritis disease activity scores",
    "tail_type": "phenotype",
    "source_sentence": "Anti-TNF therapy significantly reduced RA disease activity scores.",
    "score": 100
  }
]
```

---

## Input
```
{Unraveling the immunological landscape and gut microbiome in sepsis: a comprehensive approach to diagnosis and prognosis. Background Comprehensive and in-depth research on the immunophenotype of septic patients remains limited, and effective biomarkers for the diagnosis and treatment of sepsis are urgently needed in clinical practice. Methods Blood samples from 31 septic patients in the Intensive Care Unit (ICU), 25 non-septic ICU patients, and 18 healthy controls were analyzed using flow cytometry for deep immunophenotyping. Metagenomic sequencing was performed in 41 fecal samples, including 13 septic patients, 10 non-septic ICU patients, and 18 healthy controls. Immunophenotype shifts were evaluated using differential expression sliding window analysis, and random forest models were developed for sepsis diagnosis or prognosis prediction. Findings Septic patients exhibited decreased proportions of natural killer (NK) cells and plasmacytoid dendritic cells (pDCs) in CD45+ leukocytes compared with non-septic ICU patients and healthy controls. These changes statistically mediated the association of Bacteroides salyersiae with sepsis, suggesting a potential underlying mechanism. A combined diagnostic model incorporating B.salyersia, NK cells in CD45+ leukocytes, and C-reactive protein (CRP) demonstrated high accuracy in distinguishing sepsis from non-sepsis (area under the receiver operating characteristic curve, AUC = 0.950, 95% CI: 0.811–1.000). Immunophenotyping and disease severity analysis identified an Acute Physiology and Chronic Health Evaluation (APACHE) II score threshold of 21, effectively distinguishing mild (n = 19) from severe (n = 12) sepsis. A prognostic model based on the proportion of total lymphocytes, Helper T (Th) 17 cells, CD4+ effector memory T (TEM) cells, and Th1 cells in CD45+ leukocytes achieved robust outcome prediction (AUC = 0.906, 95% CI: 0.732–1.000), with further accuracy improvement when combined with clinical scores (AUC = 0.938, 95% CI: 0.796–1.000). Interpretation NK cell subsets within innate immunity exhibit significant diagnostic value for sepsis, particularly when combined with B. salyersiae and CRP. In addition, T cell phenotypes within adaptive immunity are correlated with sepsis severity and may serve as reliable prognostic markers.}
```