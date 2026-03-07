# Data Preparation Steering File - AushadhiMitra

## Purpose
Pre-load reference data, IMPPAT phytochemical records, and curated hero scenarios into S3, DynamoDB, and PostgreSQL before system deployment.

## Data Sources Overview

### 1. S3 Reference Files
**Bucket**: `ausadhi-mitra-667736132441`  
**Region**: us-east-1

### 2. DynamoDB IMPPAT Database
**Table**: `ausadhi-imppat`  
**Region**: us-east-1

### 3. PostgreSQL Curated Database
**Host**: `scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com`  
**Database**: `aushadhimitra`

---

## S3 Reference Data

### File 1: name_mappings.json
**Path**: `s3://ausadhi-mitra-667736132441/reference/name_mappings.json`

**Purpose**: Map common/brand names to scientific names for 5 key AYUSH plants

**Schema**:
```json
{
  "plants": [
    {
      "scientific_name": "Curcuma longa",
      "common_names": ["Turmeric", "Haldi", "Haridra"],
      "hindi_name": "हल्दी",
      "brand_names": ["Himalaya Turmeric", "Organic India Turmeric"],
      "key_phytochemicals": ["Curcumin", "Demethoxycurcumin", "Bisdemethoxycurcumin"],
      "primary_uses": ["Anti-inflammatory", "Antioxidant", "Digestive health"]
    },
    {
      "scientific_name": "Glycyrrhiza glabra",
      "common_names": ["Licorice", "Mulethi", "Yashtimadhu"],
      "hindi_name": "मुलेठी",
      "brand_names": ["Himalaya Yashtimadhu"],
      "key_phytochemicals": ["Glycyrrhizin", "Glabridin"],
      "primary_uses": ["Respiratory health", "Digestive health", "Anti-inflammatory"]
    },
    {
      "scientific_name": "Zingiber officinale",
      "common_names": ["Ginger", "Adrak", "Shunthi"],
      "hindi_name": "अदरक",
      "brand_names": ["Organic India Ginger"],
      "key_phytochemicals": ["Gingerol", "Shogaol", "Zingerone"],
      "primary_uses": ["Digestive health", "Anti-nausea", "Anti-inflammatory"]
    },
    {
      "scientific_name": "Hypericum perforatum",
      "common_names": ["St. John's Wort"],
      "hindi_name": "सेंट जॉन्स वॉर्ट",
      "brand_names": ["Nature's Way St. John's Wort"],
      "key_phytochemicals": ["Hypericin", "Hyperforin"],
      "primary_uses": ["Mood support", "Mild depression"]
    },
    {
      "scientific_name": "Withania somnifera",
      "common_names": ["Ashwagandha", "Indian Ginseng", "Asgandh"],
      "hindi_name": "अश्वगंधा",
      "brand_names": ["Himalaya Ashwagandha", "Organic India Ashwagandha"],
      "key_phytochemicals": ["Withanolides", "Withaferin A"],
      "primary_uses": ["Stress relief", "Adaptogen", "Energy"]
    }
  ]
}
```

### File 2: cyp_enzymes.json
**Path**: `s3://ausadhi-mitra-667736132441/reference/cyp_enzymes.json`

**Purpose**: Define CYP450 enzymes with severity weights for interaction scoring

**Schema**:
```json
{
  "enzymes": [
    {
      "enzyme_id": "CYP3A4",
      "full_name": "Cytochrome P450 3A4",
      "metabolizes_percent": 50,
      "severity_weight": 20,
      "common_substrates": ["Cyclosporine", "Tacrolimus", "Simvastatin", "Midazolam"],
      "clinical_significance": "Most abundant CYP enzyme; metabolizes ~50% of drugs"
    },
    {
      "enzyme_id": "CYP2D6",
      "full_name": "Cytochrome P450 2D6",
      "metabolizes_percent": 25,
      "severity_weight": 18,
      "common_substrates": ["Codeine", "Tramadol", "Metoprolol", "Fluoxetine"],
      "clinical_significance": "Highly polymorphic; genetic variation affects metabolism"
    },
    {
      "enzyme_id": "CYP2C9",
      "full_name": "Cytochrome P450 2C9",
      "metabolizes_percent": 15,
      "severity_weight": 22,
      "common_substrates": ["Warfarin", "Phenytoin", "Losartan", "Glipizide"],
      "clinical_significance": "Metabolizes many NTI drugs; high clinical impact"
    },
    {
      "enzyme_id": "CYP2C19",
      "full_name": "Cytochrome P450 2C19",
      "metabolizes_percent": 10,
      "severity_weight": 15,
      "common_substrates": ["Clopidogrel", "Omeprazole", "Diazepam"],
      "clinical_significance": "Polymorphic; affects proton pump inhibitor metabolism"
    },
    {
      "enzyme_id": "CYP1A2",
      "full_name": "Cytochrome P450 1A2",
      "metabolizes_percent": 5,
      "severity_weight": 12,
      "common_substrates": ["Theophylline", "Caffeine", "Clozapine"],
      "clinical_significance": "Induced by smoking; inhibited by grapefruit"
    },
    {
      "enzyme_id": "CYP2B6",
      "full_name": "Cytochrome P450 2B6",
      "metabolizes_percent": 3,
      "severity_weight": 10,
      "common_substrates": ["Bupropion", "Efavirenz", "Ketamine"],
      "clinical_significance": "Metabolizes some antidepressants and antiretrovirals"
    },
    {
      "enzyme_id": "CYP2E1",
      "full_name": "Cytochrome P450 2E1",
      "metabolizes_percent": 2,
      "severity_weight": 8,
      "common_substrates": ["Acetaminophen", "Ethanol"],
      "clinical_significance": "Induced by chronic alcohol use"
    },
    {
      "enzyme_id": "CYP2A6",
      "full_name": "Cytochrome P450 2A6",
      "metabolizes_percent": 1,
      "severity_weight": 5,
      "common_substrates": ["Nicotine", "Coumarin"],
      "clinical_significance": "Metabolizes nicotine and some anticoagulants"
    },
    {
      "enzyme_id": "CYP2C8",
      "full_name": "Cytochrome P450 2C8",
      "metabolizes_percent": 1,
      "severity_weight": 10,
      "common_substrates": ["Paclitaxel", "Repaglinide"],
      "clinical_significance": "Metabolizes some anticancer and antidiabetic drugs"
    },
    {
      "enzyme_id": "CYP3A5",
      "full_name": "Cytochrome P450 3A5",
      "metabolizes_percent": 1,
      "severity_weight": 8,
      "common_substrates": ["Tacrolimus", "Midazolam"],
      "clinical_significance": "Similar to CYP3A4; polymorphic expression"
    }
  ]
}
```

### File 3: nti_drugs.json
**Path**: `s3://ausadhi-mitra-667736132441/reference/nti_drugs.json`

**Purpose**: List Narrow Therapeutic Index drugs requiring +25 severity points

**Schema**:
```json
{
  "nti_drugs": [
    {
      "drug_name": "Warfarin",
      "generic_name": "Warfarin sodium",
      "therapeutic_class": "Anticoagulant",
      "primary_cyp": ["CYP2C9", "CYP3A4"],
      "clinical_concern": "Bleeding risk with elevated levels; thrombosis risk with decreased levels",
      "monitoring": "INR (International Normalized Ratio)"
    },
    {
      "drug_name": "Cyclosporine",
      "generic_name": "Cyclosporine",
      "therapeutic_class": "Immunosuppressant",
      "primary_cyp": ["CYP3A4"],
      "clinical_concern": "Organ rejection risk with decreased levels; nephrotoxicity with elevated levels",
      "monitoring": "Serum cyclosporine levels"
    },
    {
      "drug_name": "Digoxin",
      "generic_name": "Digoxin",
      "therapeutic_class": "Cardiac glycoside",
      "primary_cyp": ["P-glycoprotein transporter"],
      "clinical_concern": "Arrhythmia and toxicity with elevated levels",
      "monitoring": "Serum digoxin levels, ECG"
    },
    {
      "drug_name": "Theophylline",
      "generic_name": "Theophylline",
      "therapeutic_class": "Bronchodilator",
      "primary_cyp": ["CYP1A2", "CYP2E1"],
      "clinical_concern": "Seizures and arrhythmia with elevated levels",
      "monitoring": "Serum theophylline levels"
    },
    {
      "drug_name": "Lithium",
      "generic_name": "Lithium carbonate",
      "therapeutic_class": "Mood stabilizer",
      "primary_cyp": ["Renal excretion (not CYP)"],
      "clinical_concern": "Neurotoxicity with elevated levels",
      "monitoring": "Serum lithium levels"
    },
    {
      "drug_name": "Phenytoin",
      "generic_name": "Phenytoin sodium",
      "therapeutic_class": "Anticonvulsant",
      "primary_cyp": ["CYP2C9", "CYP2C19"],
      "clinical_concern": "Seizures with decreased levels; toxicity with elevated levels",
      "monitoring": "Serum phenytoin levels"
    },
    {
      "drug_name": "Carbamazepine",
      "generic_name": "Carbamazepine",
      "therapeutic_class": "Anticonvulsant",
      "primary_cyp": ["CYP3A4"],
      "clinical_concern": "Seizures with decreased levels; toxicity with elevated levels",
      "monitoring": "Serum carbamazepine levels"
    },
    {
      "drug_name": "Tacrolimus",
      "generic_name": "Tacrolimus",
      "therapeutic_class": "Immunosuppressant",
      "primary_cyp": ["CYP3A4", "CYP3A5"],
      "clinical_concern": "Organ rejection with decreased levels; nephrotoxicity with elevated levels",
      "monitoring": "Serum tacrolimus levels"
    },
    {
      "drug_name": "Levothyroxine",
      "generic_name": "Levothyroxine sodium",
      "therapeutic_class": "Thyroid hormone",
      "primary_cyp": ["Not CYP-metabolized"],
      "clinical_concern": "Hypothyroidism with decreased levels; hyperthyroidism with elevated levels",
      "monitoring": "TSH, Free T4"
    },
    {
      "drug_name": "Clozapine",
      "generic_name": "Clozapine",
      "therapeutic_class": "Antipsychotic",
      "primary_cyp": ["CYP1A2", "CYP3A4"],
      "clinical_concern": "Agranulocytosis risk; seizures with elevated levels",
      "monitoring": "Serum clozapine levels, WBC count"
    }
  ]
}
```

---

## DynamoDB IMPPAT Data

### Table Schema
```
Table: ausadhi-imppat
Partition Key: plant_name (String)
Sort Key: record_key (String)
```

### Record Types

#### 1. METADATA Record
```json
{
  "plant_name": "curcuma_longa",
  "record_key": "METADATA",
  "scientific_name": "Curcuma longa",
  "common_name": "Turmeric",
  "family": "Zingiberaceae",
  "phytochemical_count": 235,
  "last_updated": "2024-01-15T00:00:00Z"
}
```

#### 2. PHYTO#<id> Records
```json
{
  "plant_name": "curcuma_longa",
  "record_key": "PHYTO#IMPPAT0001",
  "phytochemical_name": "Curcumin",
  "plant_part": "Rhizome",
  "imppat_id": "IMPPAT0001",
  "smiles": "COC1=C(C=CC(=C1)C=CC(=O)CC(=O)C=CC2=CC(=C(C=C2)O)OC)O",
  "molecular_weight": 368.38,
  "drug_likeness": 0.85,
  "admet_properties": {
    "absorption": "Moderate",
    "distribution": "High protein binding",
    "metabolism": "Hepatic via CYP450",
    "excretion": "Biliary and renal",
    "toxicity": "Low"
  },
  "cyp_interactions": {
    "inhibits": ["CYP2C9", "CYP3A4"],
    "induces": [],
    "substrates": ["CYP3A4"]
  }
}
```

### Plants to Load (Minimum 5)
1. **Curcuma longa** (Turmeric) - ~235 phytochemicals
2. **Glycyrrhiza glabra** (Licorice) - ~180 phytochemicals
3. **Zingiber officinale** (Ginger) - ~150 phytochemicals
4. **Hypericum perforatum** (St. John's Wort) - ~120 phytochemicals
5. **Withania somnifera** (Ashwagandha) - ~95 phytochemicals

### Loading Script
**File**: `scripts/imppat_pipeline.py`

**Usage**:
```bash
python scripts/imppat_pipeline.py \
  --csv data/imppat_raw.csv \
  --table ausadhi-imppat \
  --region us-east-1
```

**Process**:
1. Parse IMPPAT CSV file
2. Extract plant metadata
3. Extract phytochemical records with CYP data
4. Batch write to DynamoDB (25 items per batch)
5. Verify record counts

---

## PostgreSQL Curated Database

### Table: curated_interactions

**Schema**:
```sql
CREATE TABLE curated_interactions (
  interaction_key VARCHAR(255) PRIMARY KEY,
  ayush_name VARCHAR(255) NOT NULL,
  allopathy_name VARCHAR(255) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  response_data JSONB NOT NULL,
  knowledge_graph JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ayush_name ON curated_interactions(ayush_name);
CREATE INDEX idx_allopathy_name ON curated_interactions(allopathy_name);
CREATE INDEX idx_severity ON curated_interactions(severity);
```

### Hero Scenarios to Load (Minimum 10-15)

#### 1. Turmeric + Warfarin (MAJOR)
```json
{
  "interaction_key": "curcuma_longa:warfarin",
  "ayush_name": "Curcuma longa",
  "allopathy_name": "Warfarin",
  "severity": "MAJOR",
  "response_data": {
    "severity": {
      "level": "MAJOR",
      "score": 75,
      "factors": ["CYP2C9 overlap", "NTI drug", "Anticoagulant PD overlap", "Clinical evidence"]
    },
    "mechanisms": [
      {
        "type": "CYP",
        "enzyme": "CYP2C9",
        "effect": "Curcumin inhibits CYP2C9; Warfarin is CYP2C9 substrate → elevated Warfarin levels → bleeding risk"
      },
      {
        "type": "Pharmacodynamic",
        "effect": "Both have anticoagulant properties → additive bleeding risk"
      }
    ],
    "clinical_effects": "Increased INR, prolonged bleeding time, risk of hemorrhage",
    "action_recommendation": "Avoid combination. If unavoidable, monitor INR closely and adjust Warfarin dose.",
    "disclaimer": "This tool provides informational analysis only. Consult a licensed healthcare professional before making any medication decisions."
  },
  "knowledge_graph": {
    "nodes": [
      {"id": "plant_1", "label": "Turmeric", "type": "Plant"},
      {"id": "phyto_1", "label": "Curcumin", "type": "Phytochemical"},
      {"id": "drug_1", "label": "Warfarin", "type": "Drug"},
      {"id": "cyp_1", "label": "CYP2C9", "type": "CYP_Enzyme", "is_overlap": true}
    ],
    "edges": [
      {"source": "plant_1", "target": "phyto_1", "relationship": "CONTAINS"},
      {"source": "phyto_1", "target": "cyp_1", "relationship": "INHIBITS"},
      {"source": "drug_1", "target": "cyp_1", "relationship": "METABOLIZED_BY"}
    ],
    "overlap_nodes": ["cyp_1"]
  }
}
```

#### 2. St. John's Wort + Cyclosporine (MAJOR)
```json
{
  "interaction_key": "hypericum_perforatum:cyclosporine",
  "ayush_name": "Hypericum perforatum",
  "allopathy_name": "Cyclosporine",
  "severity": "MAJOR",
  "response_data": {
    "severity": {
      "level": "MAJOR",
      "score": 85,
      "factors": ["CYP3A4 induction", "NTI drug", "Organ rejection risk", "Clinical case reports"]
    },
    "mechanisms": [
      {
        "type": "CYP",
        "enzyme": "CYP3A4",
        "effect": "Hyperforin induces CYP3A4 → decreased Cyclosporine levels → organ rejection risk"
      }
    ],
    "clinical_effects": "Subtherapeutic Cyclosporine levels, acute organ rejection in transplant patients",
    "action_recommendation": "CONTRAINDICATED. Do not use together. Organ rejection risk is life-threatening.",
    "disclaimer": "This tool provides informational analysis only. Consult a licensed healthcare professional before making any medication decisions."
  },
  "knowledge_graph": {
    "nodes": [
      {"id": "plant_1", "label": "St. John's Wort", "type": "Plant"},
      {"id": "phyto_1", "label": "Hyperforin", "type": "Phytochemical"},
      {"id": "drug_1", "label": "Cyclosporine", "type": "Drug"},
      {"id": "cyp_1", "label": "CYP3A4", "type": "CYP_Enzyme", "is_overlap": true}
    ],
    "edges": [
      {"source": "plant_1", "target": "phyto_1", "relationship": "CONTAINS"},
      {"source": "phyto_1", "target": "cyp_1", "relationship": "INDUCES"},
      {"source": "drug_1", "target": "cyp_1", "relationship": "METABOLIZED_BY"}
    ],
    "overlap_nodes": ["cyp_1"]
  }
}
```

#### 3. Licorice + Digoxin (MAJOR)
```json
{
  "interaction_key": "glycyrrhiza_glabra:digoxin",
  "ayush_name": "Glycyrrhiza glabra",
  "allopathy_name": "Digoxin",
  "severity": "MAJOR",
  "response_data": {
    "severity": {
      "level": "MAJOR",
      "score": 80,
      "factors": ["Potassium depletion", "NTI drug", "Arrhythmia risk", "Clinical evidence"]
    },
    "mechanisms": [
      {
        "type": "Electrolyte",
        "effect": "Glycyrrhizin causes potassium depletion → hypokalemia → increased Digoxin toxicity → fatal arrhythmia"
      }
    ],
    "clinical_effects": "Hypokalemia, ventricular arrhythmia, digitalis toxicity",
    "action_recommendation": "Avoid combination. Monitor potassium levels and ECG if unavoidable.",
    "disclaimer": "This tool provides informational analysis only. Consult a licensed healthcare professional before making any medication decisions."
  },
  "knowledge_graph": {
    "nodes": [
      {"id": "plant_1", "label": "Licorice", "type": "Plant"},
      {"id": "phyto_1", "label": "Glycyrrhizin", "type": "Phytochemical"},
      {"id": "drug_1", "label": "Digoxin", "type": "Drug"},
      {"id": "electrolyte_1", "label": "Potassium", "type": "Electrolyte", "is_overlap": true}
    ],
    "edges": [
      {"source": "plant_1", "target": "phyto_1", "relationship": "CONTAINS"},
      {"source": "phyto_1", "target": "electrolyte_1", "relationship": "DEPLETES"},
      {"source": "drug_1", "target": "electrolyte_1", "relationship": "SENSITIVE_TO"}
    ],
    "overlap_nodes": ["electrolyte_1"]
  }
}
```

### Loading Script
**File**: `scripts/load_curated_interactions.py`

**Usage**:
```bash
python scripts/load_curated_interactions.py \
  --host scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com \
  --database aushadhimitra \
  --user <username> \
  --password <password>
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] S3 bucket created: `ausadhi-mitra-667736132441`
- [ ] DynamoDB table created: `ausadhi-imppat`
- [ ] PostgreSQL database created: `aushadhimitra`
- [ ] IAM roles configured for Lambda access

### S3 Upload
- [ ] Upload `name_mappings.json` to S3
- [ ] Upload `cyp_enzymes.json` to S3
- [ ] Upload `nti_drugs.json` to S3
- [ ] Verify S3 bucket permissions (Lambda read access)

### DynamoDB Load
- [ ] Run `imppat_pipeline.py` for Curcuma longa
- [ ] Run `imppat_pipeline.py` for Glycyrrhiza glabra
- [ ] Run `imppat_pipeline.py` for Zingiber officinale
- [ ] Run `imppat_pipeline.py` for Hypericum perforatum
- [ ] Run `imppat_pipeline.py` for Withania somnifera
- [ ] Verify record counts (METADATA + PHYTO records)

### PostgreSQL Load
- [ ] Create `curated_interactions` table
- [ ] Create `allopathy_cache` table
- [ ] Create `interaction_sources` table
- [ ] Load 10-15 hero scenarios
- [ ] Verify indexes created
- [ ] Test Layer 0 lookup performance (<500ms)

### Validation
- [ ] Test S3 file access from Lambda
- [ ] Test DynamoDB query performance
- [ ] Test PostgreSQL connection from Lambda
- [ ] Verify curated DB column name: `response_data` (not `interaction_data`)
- [ ] Test end-to-end query with hero scenario

---

## Maintenance

### Data Updates
- **S3 Reference Files**: Update quarterly or when new plants/drugs added
- **DynamoDB IMPPAT**: Update when IMPPAT database releases new version
- **PostgreSQL Curated**: Add new hero scenarios based on user queries

### Monitoring
- S3 access logs for reference file usage
- DynamoDB read capacity units (scale if needed)
- PostgreSQL query performance (optimize indexes)
- Allopathy cache hit rate (target >70%)

### Backup
- S3: Versioning enabled
- DynamoDB: Point-in-time recovery enabled
- PostgreSQL: Daily automated backups (7-day retention)
