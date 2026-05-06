---
name: splunk-to-dynatrace:validate-dashboards
description: Validates Splunk dashboards work with structured JSON logging and generates Dynatrace DQL equivalents. Parses SPL queries, identifies field references, validates against structured field mappings, and provides migration guidance. Use this skill when migrating dashboards from Splunk to Dynatrace or validating field name changes.
---

# Validate Dashboards Skill

Validates that Splunk dashboards will continue working after converting to structured JSON logging, and generates equivalent Dynatrace DQL queries for migration.

## Limitations

This skill uses simple text matching to identify relevant queries and may not catch all edge cases. Complex SPL logic, dynamic filters, and non-standard configurations may need manual review. Always test in non-production before deploying.

## When to Use This Skill

- Validating Splunk dashboards before deploying structured logging
- Migrating dashboards from Splunk to Dynatrace
- Checking field naming compatibility between old and new log format
- Generating Dynatrace query equivalents from SPL
- Identifying dashboard breakage risks during migration

## Validation Capabilities

### 1. Parse Splunk Dashboard Definitions

Reads Splunk dashboard exports (JSON or XML format):

- **Simple XML dashboards**: Parse `<query>` elements
- **JSON dashboards**: Parse `search` properties
- **Scheduled searches**: Parse saved search definitions
- **Alerts**: Parse alert query definitions

### 2. Extract Field References

Identifies all field references in SPL queries:

**Field extraction patterns:**
- `field=value` (search filters)
- `| stats count by field` (aggregations)
- `| eval newfield=expression` (calculations)
- `| where field > threshold` (conditions)
- `| timechart count by field` (time series)
- `| table field1, field2` (display fields)

### 3. Validate Field Mappings

Cross-references extracted fields against structured logging field mappings:

**From analyze skill output** (`05-field-naming-analysis.md`):
- Old field names (from current logs)
- New field names (after structured conversion)
- Mapping strategy (preserve, standardize, or hybrid)

**Validation checks:**
- ✅ Field exists in new structured format
- ⚠️ Field renamed (requires dashboard update)
- ❌ Field removed (dashboard will break)

### 4. Generate Dynatrace DQL Equivalents

Converts SPL queries to Dynatrace Query Language (DQL):

**SPL to DQL Translation Patterns:**

| Splunk SPL | Dynatrace DQL |
|------------|---------------|
| `index=app sourcetype=json` | `fetch logs` |
| `personId="TEST123"` | `filter person.id == "TEST123"` |
| `\| stats count by ordinanceType` | `summarize count(), by:{ordinance.type}` |
| `\| timechart count by level` | `summarize count(), by:{level, bin(timestamp, 1m)}` |
| `\| eval duration_sec=duration/1000` | `fields duration_sec = duration / 1000` |
| `\| where duration > 5000` | `filter duration > 5000` |
| `\| top 10 personId` | `summarize count(), by:{person.id} \| sort count desc \| limit 10` |

## Splunk Object Backup Repository

**FamilySearch Convention**: Splunk objects are backed up in the [paas-splunk-object-backup](https://github.com/fs-eng/paas-splunk-object-backup) repository.

**Repository Structure**:
```
paas-splunk-object-backup/
└── nobody/                    # Shared Splunk objects by application
    └── {app-name}/            # e.g., fs-turbo, fs-prod, etc.
        ├── data/
        │   └── ui/
        │       └── views/     # Dashboard XML files
        │           └── *.xml
        ├── savedsearches.conf # Alerts and scheduled searches
        ├── macros.conf        # Splunk macros
        ├── props.conf         # Field extractions
        └── transforms.conf    # Data transforms
```

**Scope**: This skill validates **only shared objects in the 'nobody' directory**. Individual developer queries, private dashboards, and ad-hoc searches are NOT evaluated.

## Skill Workflow

### Step 1: Identify Splunk Application and Validate Repository

**Critical: Always start by identifying the Splunk application.**

1. **Ask user for Splunk application name**:
   ```
   "Which Splunk application contains the dashboards to validate?
   (e.g., fs-turbo, fs-prod, lynx-prod, etc.)"
   ```

2. **Validate repository path exists**:
   ```bash
   ls ~/github/paas-splunk-object-backup/nobody/{app-name}/
   ```
   
   **If repository not cloned**:
   ```bash
   cd ~/github
   git clone git@github.com:fs-eng/paas-splunk-object-backup.git
   ```

3. **Count dashboards and alerts**:
   ```bash
   # Count dashboards
   find ~/github/paas-splunk-object-backup/nobody/{app-name}/data/ui/views/ -name "*.xml" | wc -l
   
   # Count saved searches/alerts
   grep -c "^\[" ~/github/paas-splunk-object-backup/nobody/{app-name}/savedsearches.conf
   ```

4. **Check for blueprint.yml (optional context)**:
   
   If working from a repository root, check for `blueprint.yml`:
   ```bash
   test -f blueprint.yml && echo "Found blueprint" || echo "No blueprint"
   ```
   
   **If found**, read basic context:
   ```yaml
   name: gofr  # Blueprint name
   systems:
     - name: canary
       properties:
         services:
           webapp: ...    # Service names under this system
   ```
   
   **Report to user**:
   ```
   "I found blueprint.yml for the '{blueprint-name}' blueprint. 
   
   Services that may produce logs:
   - {blueprint}-{system}-{service} (e.g., gofr-canary-webapp)
   - {blueprint}-{system}-{service} (e.g., gofr-production-webapp)
   
   Note: Splunk queries may use hostname patterns like '{blueprint}-{system}-{service}-*' 
   or source paths like '/var/log/{service}/*'. I'll use simple text matching to flag 
   potentially relevant queries, but this is low-confidence - you must manually verify."
   ```
   
   **If not found**, skip this step and proceed with filename-based filtering only.

5. **Inform user of scope**:
   ```
   "Found {N} dashboards and {M} saved searches in {app-name} application.
   
   Note: Validation covers shared objects in 'nobody' directory only.
   Dashboard filtering is filename-based, so dashboards with generic names
   may be missed and will need manual review.
   
   Would you like to:
   A. Validate all dashboards for a specific service (e.g., 'gofr')
   B. Validate all dashboards in the application (may take longer)
   C. Validate specific dashboards (you provide names)"
   ```

### Step 2: Filter to Service-Specific Dashboards (Filename-Based)

**For large Splunk applications (>20 dashboards), filter to service-specific dashboards first.**

1. **Ask user for service name pattern**:
   ```
   "What service are you migrating? (e.g., 'gofr', 'suggest', 'watch', etc.)
   I'll filter dashboards with this name in the filename."
   ```

2. **List matching dashboards**:
   ```bash
   ls ~/github/paas-splunk-object-backup/nobody/{app-name}/data/ui/views/ | grep -i {service-name}
   ```

3. **List matching saved searches**:
   ```bash
   grep "^\[.*{service-name}" ~/github/paas-splunk-object-backup/nobody/{app-name}/savedsearches.conf
   ```

4. **List dashboards NOT analyzed (for manual review)**:
   ```bash
   ls ~/github/paas-splunk-object-backup/nobody/{app-name}/data/ui/views/ | grep -v -i {service-name}
   ```

5. **Confirm scope with user**:
   ```
   "Found {N} dashboards matching '{service-name}' in filename:
   
   Dashboards to validate:
   - {dashboard1}.xml ({size})
   - {dashboard2}.xml ({size})
   
   Saved Searches to validate:
   - {alert1}
   - {alert2}
   
   ⚠️ Dashboards NOT analyzed ({X} total):
   - platform_overview.xml (may contain {service} queries - manual review needed)
   - system_health.xml (may contain {service} queries - manual review needed)
   - ... ({X-2} more)
   
   These dashboards have generic names and may contain queries for your service.
   You should manually check them after this validation completes.
   
   Validate the {N} matching dashboards and {M} saved searches? (y/n)"
   ```

### Step 3: Parse Dashboards and Identify Query Types

**Important: Distinguish between metrics queries and application log queries.**

For each dashboard:

1. **Check file size**:
   - If >50KB: Use targeted reading (grep for `<query>` tags)
   - If <50KB: Read full file

2. **Identify query types**:
   - **Metrics queries**: `| mstats`, `| mcatalog`, `metric_name=*`
     - ✅ **NOT affected by structured logging changes** - skip validation
   - **Application log queries**: `index=`, `source=`, `sourcetype=`, SPL commands
     - ⚠️ **MUST validate** - field names may change

3. **Extract application log queries only**:
   ```bash
   # For large dashboards, extract query tags only
   grep -A 20 "<query>" dashboard.xml | grep -v "mstats"
   ```

4. **Expand Splunk macros**:
   - Read `macros.conf` to get macro definitions
   - Replace macro calls like `` `app_index` `` with actual SPL
   - Example:
     ```
     Macro: `gofr-metric-report`
     Definition: index=main sourcetype=json source="/var/log/fs/business-events.json"
     ```

5. **Perform simple query relevance check (best-effort)**:
   
   **For each application log query, use simple text matching**:
   - Contains blueprint name (e.g., "gofr")? → **Likely relevant**
   - Contains service name (e.g., "webapp")? → **Likely relevant**
   - Contains hostname pattern (e.g., "gofr-canary-webapp-*")? → **Likely relevant**
   - Only shared index with no filters (e.g., "index=production")? → **⚠️ Unclear - manual review required**
   
   **Assign confidence level**:
   - **HIGH**: Dedicated service index (`index=gofr`) or exact hostname match
   - **MEDIUM**: Pattern match (contains service name, source path with service)
   - **LOW**: Shared index without obvious service filters
   
   **Important**: This is SIMPLE TEXT MATCHING only. Cannot handle:
   - Complex SPL logic (subsearches, eval conditions)
   - Non-standard hostname patterns
   - Queries that filter service data through other means

6. **Report query distribution**:
   ```
   "Dashboard: {name}
   - Total panels: {total}
   - Metrics queries: {N} (skipped - not affected by log format changes)
   - Application log queries: {M} total
     - Likely relevant (HIGH/MEDIUM confidence): {X}
     - Unclear (LOW confidence - manual review required): {Y}
   
   ⚠️ Note: Relevance detection uses simple text matching and may be incorrect.
   All queries marked LOW confidence require manual verification.
   
   Proceeding to validate field references in all {M} application log queries..."
   ```

### Step 4: Parse SPL Queries and Extract Field References

For each **application log query** (skip metrics queries):

1. **Identify query type**:
   - Search: `index=... | search ...`
   - Stats: `| stats count by field`
   - Timechart: `| timechart count by field`
   - Table: `| table field1, field2`
   - Alert: `| where condition | eval threshold`

2. **Extract field references**:
   - Search clauses: `personId="..."`, `level=ERROR`
   - Aggregation fields: `count by ordinanceType`
   - Display fields: `table personId, timestamp, message`
   - Calculated fields: `eval duration_sec=duration/1000`
   - Filter conditions: `where duration > 5000`

3. **Normalize field names**:
   - Handle quoted fields: `"person.id"`
   - Handle aliased fields: `rename personId as person_id`
   - Handle nested fields: `json.field.nested`

4. **Check for business event routing**:
   - If query references business event macro or source (e.g., `gofr-metric-report`, `/var/log/fs/business-events.json`)
   - Verify logback configuration routes business events to separate file
   - Note: Business events may have different field sets than application logs

### Step 5: Load Field Mapping Context

Read field naming analysis from analyze skill output:

**From `05-field-naming-analysis.md`:**
```markdown
## Field Naming Mappings

### Current Field Names → New Field Names

| Current Name | New Name (Option 1) | Preserve (Option 2) | Hybrid (Option 3) |
|--------------|---------------------|---------------------|-------------------|
| personId | person.id | personId | both |
| ordinanceType | ordinance.type | ordinanceType | both |
| requestCount | request.count | requestCount | both |
```

**Field mapping strategy** chosen during conversion (Option 1, 2, or 3).

### Step 6: Validate Each Dashboard Query

For each dashboard and query:

1. **Report query relevance (from Step 3)**:
   ```markdown
   #### Query Relevance (Best-Effort)
   
   **Pattern Detected**: host=*gofr* (appears to target this service)
   **Confidence**: MEDIUM - text matching found service name in hostname filter
   **Note**: Verify this query filters to {service} in actual Splunk
   ```
   
   OR for unclear queries:
   ```markdown
   #### Query Relevance (Simple Text Matching)
   
   **Pattern Detected**: index=production (no service-specific filter detected)
   **Confidence**: LOW - shared index without obvious service identifiers
   **Note**: Manually verify if this query includes {service} data
   ```

2. **Check field existence**:
   - Does each referenced field exist in new structured format?
   - If renamed, is mapping documented?

3. **Assess breakage risk**:
   - ✅ **GREEN (No Risk)**: Field preserved with same name or value
   - ⚠️ **YELLOW (Low Risk)**: Field renamed, dashboard needs simple find/replace
   - ❌ **RED (High Risk)**: Field removed, query logic needs rework or redesign

4. **Generate required updates**:
   - Find/replace operations for renamed fields
   - Query rewrite suggestions for removed fields
   - Equivalent Dynatrace DQL query (with disclaimer to test before use)

### Step 7: Parse Saved Searches and Alerts

**Don't forget alerts** - they're in `savedsearches.conf` and also need validation.

1. **Read savedsearches.conf**:
   ```bash
   # Count alert definitions
   grep -c "^\[" savedsearches.conf
   
   # Filter to service-specific alerts
   grep "^\[.*{service-name}" savedsearches.conf
   ```

2. **Extract alert queries**:
   - Look for `search = ` field in each stanza
   - Parse SPL query same as dashboard queries
   - Extract field references

3. **Validate alert fields** using same process as dashboards

4. **Note alert-specific fields**:
   - `alert.severity`
   - `alert.suppress.fields`
   - `action.email.to`
   - These may also reference log fields

### Step 8: Generate Validation Report

Create comprehensive report with:

**Report Header**:
```markdown
# Dashboard Validation Report

**Limitations**: This analysis uses simple text matching to identify relevant queries.
Complex SPL logic, dynamic filters, and non-standard configurations may need manual review.
Always test in non-production before deploying to production.
```

**Report sections**:
- **Scope statement**: "Validated shared objects in 'nobody' directory only" + list of unanalyzed dashboards
- **Application context**: Splunk app name, total dashboards/alerts, blueprint info (if available)
- **Service filter**: Which service was validated (if filtered)
- **Query type breakdown**: Metrics vs application logs
- **Query relevance summary**: HIGH/MEDIUM/LOW confidence counts
- Dashboard inventory (name, panels, metrics vs log queries)
- Alert inventory (alert names, triggers, fields referenced)
- Field reference analysis per query (with relevance confidence level)
- Breakage risk assessment (GREEN/YELLOW/RED with clear definitions)
- Required updates for each dashboard/alert
- Dynatrace DQL equivalents
- **Action items and next steps at end**

**Risk Definitions** (include in report):
- ✅ **GREEN (No Risk)**: Field preserved with same name/value - no changes needed
- ⚠️ **YELLOW (Low Risk)**: Field renamed - simple find/replace in dashboard XML
- ❌ **RED (High Risk)**: Field removed or semantic change - requires manual query rewrite

**Query Relevance Levels** (include in report):
- **HIGH**: Dedicated service index or exact hostname match
- **MEDIUM**: Pattern match (service name in query, source path)
- **LOW**: Shared index without obvious service filters - **REQUIRES MANUAL REVIEW**

### Step 9: Generate Dynatrace Migration Guide

For each dashboard, provide:

- Original Splunk dashboard definition
- Updated Splunk dashboard (with new field names)
- Equivalent Dynatrace dashboard (DQL queries)
- Migration checklist (steps to recreate in Dynatrace)

## SPL to DQL Translation Guide

### Basic Search and Filter

**Splunk SPL:**
```spl
index=gofr sourcetype=json level=ERROR personId="TEST123"
```

**Dynatrace DQL:**
```dql
fetch logs
| filter level == "ERROR" and person.id == "TEST123"
```

### Aggregation by Field

**Splunk SPL:**
```spl
index=gofr sourcetype=json
| stats count by ordinanceType
```

**Dynatrace DQL:**
```dql
fetch logs
| summarize count(), by:{ordinance.type}
```

### Time Series Chart

**Splunk SPL:**
```spl
index=gofr sourcetype=json level=ERROR
| timechart span=5m count by ordinanceType
```

**Dynatrace DQL:**
```dql
fetch logs
| filter level == "ERROR"
| summarize count(), by:{ordinance.type, bin(timestamp, 5m)}
```

### Top Values

**Splunk SPL:**
```spl
index=gofr sourcetype=json
| top 10 personId
```

**Dynatrace DQL:**
```dql
fetch logs
| summarize count(), by:{person.id}
| sort count desc
| limit 10
```

### Calculated Fields

**Splunk SPL:**
```spl
index=gofr sourcetype=json
| eval duration_sec=duration/1000
| where duration_sec > 5
| stats avg(duration_sec) by ordinanceType
```

**Dynatrace DQL:**
```dql
fetch logs
| fields duration_sec = duration / 1000
| filter duration_sec > 5
| summarize avg(duration_sec), by:{ordinance.type}
```

### Error Rate Percentage

**Splunk SPL:**
```spl
index=gofr sourcetype=json
| stats count(eval(level="ERROR")) as errors, count as total
| eval error_rate=round(errors/total*100, 2)
```

**Dynatrace DQL:**
```dql
fetch logs
| summarize errors = countIf(level == "ERROR"), total = count()
| fields error_rate = errors / total * 100
```

### Field Existence Check

**Splunk SPL:**
```spl
index=gofr sourcetype=json personId=*
```

**Dynatrace DQL:**
```dql
fetch logs
| filter isNotNull(person.id)
```

### Multiple Conditions

**Splunk SPL:**
```spl
index=gofr sourcetype=json (level=ERROR OR level=WARN) duration>5000
```

**Dynatrace DQL:**
```dql
fetch logs
| filter (level == "ERROR" or level == "WARN") and duration > 5000
```

## Validation Report Format

Generate `dashboard-validation-report.md`:

```markdown
# Dashboard Validation Report

**Application**: GOFR
**Date**: 2026-05-04
**Field Naming Strategy**: Option 1 (dot.notation)

## Executive Summary

- **Total Dashboards**: 8
- **Total Queries**: 23
- **Queries Requiring Updates**: 15
- **High Risk Queries**: 2
- **Low Risk Queries**: 13
- **No Risk Queries**: 8

## Dashboard Inventory

### Dashboard 1: Ordinance Request Monitoring

**Owner**: Operations Team
**Panels**: 4
**Risk Level**: ⚠️ Low Risk (field renames only)

#### Panel 1: Error Rate by Ordinance Type

**Current SPL Query:**
```spl
index=gofr sourcetype=json level=ERROR
| stats count by ordinanceType
```

**Field References**: `ordinanceType`

**Validation**:
- ⚠️ Field `ordinanceType` renamed to `ordinance.type`

**Required Update**:
```spl
index=gofr sourcetype=json level=ERROR
| stats count by ordinance.type
```

**Dynatrace DQL Equivalent:**
```dql
fetch logs
| filter level == "ERROR"
| summarize count(), by:{ordinance.type}
```

**Migration Steps**:
1. In Splunk: Update query to use `ordinance.type`
2. Test updated query in Splunk after structured logging deployment
3. In Dynatrace: Create equivalent query using DQL above
4. Validate results match between Splunk and Dynatrace

---

#### Panel 2: Average Request Duration

**Current SPL Query:**
```spl
index=gofr sourcetype=json
| stats avg(duration) by ordinanceType
```

**Field References**: `duration`, `ordinanceType`

**Validation**:
- ✅ Field `duration` preserved (already structured field name)
- ⚠️ Field `ordinanceType` renamed to `ordinance.type`

**Required Update**:
```spl
index=gofr sourcetype=json
| stats avg(duration) by ordinance.type
```

**Dynatrace DQL Equivalent:**
```dql
fetch logs
| summarize avg(duration), by:{ordinance.type}
```

---

### Dashboard 2: User Activity

**Owner**: Product Analytics Team
**Panels**: 3
**Risk Level**: ❌ High Risk (field removed)

#### Panel 1: Active Users by Country

**Current SPL Query:**
```spl
index=gofr sourcetype=json
| stats dc(userId) by country
```

**Field References**: `userId`, `country`

**Validation**:
- ❌ Field `userId` removed per FamilySearch Observability Standards (PII concern)
- ⚠️ Field `country` renamed to `user.country`

**Required Update**:
```spl
# DASHBOARD NEEDS REDESIGN
# userId removed per observability standards (PII)
# Alternative: Use user.id (opaque identifier) instead
index=gofr sourcetype=json
| stats dc(user.id) by user.country
```

**Dynatrace DQL Equivalent:**
```dql
fetch logs
| summarize uniqueCount(user.id), by:{user.country}
```

**Migration Notes**:
- **Breaking Change**: `userId` field no longer available (contains PII)
- **Recommended Alternative**: Use `user.id` (opaque hash, not PII)
- **Impact**: Counts should remain accurate, but cannot correlate with actual user IDs

---

## Summary of Required Updates

### Find/Replace Operations (Low Risk)

Apply these find/replace operations to Splunk dashboards:

| Old Field Name | New Field Name | Occurrences |
|----------------|----------------|-------------|
| `ordinanceType` | `ordinance.type` | 12 |
| `personId` | `person.id` | 8 |
| `requestCount` | `request.count` | 5 |

### Manual Rewrites (High Risk)

These queries require manual redesign:

1. **Dashboard 2, Panel 1**: `userId` field removed (PII), use `user.id` instead
2. **Dashboard 5, Panel 3**: `responseTime` field removed (Dynatrace auto-captures)

## Dynatrace Migration Checklist

For each dashboard:

- [ ] Update Splunk queries with new field names
- [ ] Deploy structured logging to Splunk
- [ ] Validate updated Splunk dashboards show correct data
- [ ] Create equivalent Dynatrace dashboard using DQL queries
- [ ] Validate Dynatrace dashboard results match Splunk
- [ ] Monitor both dashboards in parallel during Phase 2
- [ ] Decommission Splunk dashboard after cutover to Dynatrace

## Next Steps

1. **Phase 1**: Update Splunk dashboards with new field names (find/replace)
2. **Deploy**: Deploy structured logging to Splunk (Phase 1)
3. **Validate**: Verify updated dashboards show correct data in Splunk
4. **Phase 2**: Create Dynatrace dashboards using DQL equivalents
5. **Parallel**: Run both Splunk and Dynatrace dashboards during dual ingestion
6. **Cutover**: Decommission Splunk dashboards after Phase 3

## References

- **Field Naming Analysis**: `05-field-naming-analysis.md`
- **FamilySearch Observability Standards**: https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295
- **Dynatrace DQL Documentation**: https://docs.dynatrace.com/docs/observe-and-explore/query-data/dynatrace-query-language
```

## Dynatrace Dashboard JSON Template

Generate Dynatrace dashboard JSON for import:

```json
{
  "dashboardMetadata": {
    "name": "GOFR - Ordinance Request Monitoring",
    "shared": true,
    "owner": "operations-team",
    "tags": ["gofr", "ordinances", "migration-from-splunk"]
  },
  "tiles": [
    {
      "name": "Error Rate by Ordinance Type",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 0,
        "left": 0,
        "width": 304,
        "height": 304
      },
      "tileFilter": {},
      "customName": "Error Rate by Ordinance Type",
      "queries": [
        {
          "id": "A",
          "metric": "logs",
          "spaceAggregation": "AUTO",
          "timeAggregation": "DEFAULT",
          "splitBy": ["ordinance.type"],
          "filterBy": {
            "filter": "level == \"ERROR\""
          }
        }
      ],
      "visualConfig": {
        "type": "GRAPH_CHART",
        "global": {},
        "rules": []
      }
    }
  ]
}
```

## Handling Large Splunk Applications

**For applications with >20 dashboards or >50 alerts:**

### Strategy 1: Service-Specific Validation (Recommended)

Validate only dashboards/alerts for the service being migrated:

1. Ask user for service name pattern (e.g., "gofr", "suggest")
2. Filter dashboards: `grep -i {service}` in views directory
3. Filter alerts: `grep "^\[.*{service}" savedsearches.conf`
4. Validate filtered subset only

**Rationale**: Reduces scope, focuses on immediate need, faster validation.

### Strategy 2: Batch Validation

If validating entire application is required:

1. **Phase 1**: Validate all dashboards (may take 30-60 minutes)
2. **Phase 2**: Validate all alerts (may take longer - 32K lines in savedsearches.conf)
3. Generate comprehensive report covering full application
4. Prioritize fixing RED (high risk) items first

**Rationale**: Complete validation for full migration planning.

### Strategy 3: Priority Validation

Focus on critical operational dashboards first:

1. Ask user: "Which dashboards are business-critical?"
2. Validate those first
3. Generate partial report with note: "Remaining dashboards pending validation"
4. Iterate on additional dashboards as needed

**Rationale**: Ensures critical monitoring is preserved, deferring nice-to-have dashboards.

## File Size Handling

**For large dashboard files (>50KB):**

1. **Don't read entire file** - expensive in tokens
2. **Use targeted grep**:
   ```bash
   # Extract query blocks only
   grep -A 20 "<query>" large_dashboard.xml > queries.txt
   
   # Filter out metrics queries
   grep -v "mstats" queries.txt > app_log_queries.txt
   ```
3. **Process extracted queries** instead of full dashboard
4. **Report file size** to user: "Dashboard is 68KB, extracted 5 application log queries for validation"

**Rationale**: Saves tokens, faster processing, focuses on relevant sections.

## Best Practices

### 1. Always Start with Scope Questions

**Critical: Don't assume scope** - ask these questions first:

1. "Which Splunk application?" → Validates repository path
2. "Which service?" → Filters to relevant dashboards/alerts
3. "Validate all or critical-only?" → Determines validation strategy
4. "Include alerts?" → Confirms whether to parse savedsearches.conf

### 2. Distinguish Metrics from Logs

**Before validating queries, identify type:**

- Metrics queries (`| mstats`): Skip - not affected
- Application log queries: Validate all fields

**Report distribution**:
```
"Dashboard has 35 panels:
- 30 metrics queries (not affected by logging changes)
- 5 application log queries (validating these)"
```

### 3. Validate Before Deploying

Don't deploy structured logging without validating dashboards first:

1. Run validation skill
2. Review report with dashboard owners
3. Update dashboards preemptively (if YELLOW/RED risks found)
4. Test with sample JSON data if possible

### 4. Communicate Breaking Changes

If field removed (RED risk), communicate clearly:

- **What changed**: Field X removed per observability standards
- **Why changed**: Reason (PII, auto-captured, etc.)
- **Alternative**: Use field Y instead
- **Impact**: Dashboard shows different data or breaks

### 5. Understand Shared vs Private Objects

**Only shared objects in 'nobody' directory are validated.**

**Include this note in every report:**
```markdown
## Validation Scope

This validation covers **only shared Splunk objects in the 'nobody' directory** from the paas-splunk-object-backup repository.

**NOT evaluated:**
- Individual developer queries (private searches)
- Personal dashboards (not in 'nobody' directory)
- Ad-hoc SPL queries run in Splunk search bar
- Dashboards owned by specific users (not shared)

**Recommendation**: Communicate to team that private/personal dashboards may break after structured logging deployment. Users should validate their own queries separately.
```

### 6. Maintain Dashboard Inventory

Keep dashboard inventory up to date:

- Dashboard name and Splunk app
- Number of panels (metrics vs log queries)
- Dependencies on specific fields
- Migration status (validated, updated, Dynatrace equivalent created)

### 7. Handle Splunk Macros Properly

**Macros obscure actual queries** - always expand them.

1. **Read macros.conf** in Splunk app directory
2. **Find macro definition**:
   ```
   [gofr-metric-report]
   definition = index=main sourcetype=json source="/var/log/fs/business-events.json"
   ```
3. **Replace macro in query**:
   ```spl
   # Before expansion
   `gofr-metric-report` | stats count by state
   
   # After expansion
   index=main sourcetype=json source="/var/log/fs/business-events.json" | stats count by state
   ```
4. **Validate expanded query** for field references

**Common macros to expand:**
- `` `app_index` `` → `index=main sourcetype=json`
- `` `{service}-metric-report` `` → business event source filter

### 8. Use Hybrid Naming During Migration

If field naming creates dashboard pain, consider hybrid approach (Option 3):

**Log both old and new field names temporarily:**
```java
logger.atInfo()
    .addKeyValue("ordinanceType", type)      // Old name (Splunk dashboards)
    .addKeyValue("ordinance.type", type)     // New name (Dynatrace)
    .log("Processing ordinance");
```

**Remove old names after dashboards updated.**

### 9. Create Dynatrace Dashboards Early

Don't wait until Phase 3 to create Dynatrace dashboards:

- Create during Phase 2 (dual ingestion)
- Validate equivalence with Splunk
- Fix any discrepancies while both systems running
- Gain confidence before decommissioning Splunk

## Common Dashboard Patterns

### Pattern 1: Error Count Over Time

**Splunk SPL:**
```spl
index=gofr sourcetype=json level=ERROR
| timechart span=5m count
```

**Dynatrace DQL:**
```dql
fetch logs
| filter level == "ERROR"
| summarize count(), by:{bin(timestamp, 5m)}
```

### Pattern 2: Top Error Messages

**Splunk SPL:**
```spl
index=gofr sourcetype=json level=ERROR
| top 10 message
```

**Dynatrace DQL:**
```dql
fetch logs
| filter level == "ERROR"
| summarize count(), by:{message}
| sort count desc
| limit 10
```

### Pattern 3: Average Latency by Service

**Splunk SPL:**
```spl
index=gofr sourcetype=json
| stats avg(duration) as avg_latency by service
| sort -avg_latency
```

**Dynatrace DQL:**
```dql
fetch logs
| summarize avg_latency = avg(duration), by:{service.name}
| sort avg_latency desc
```

### Pattern 4: Success vs Failure Rate

**Splunk SPL:**
```spl
index=gofr sourcetype=json
| eval status=if(level="ERROR", "failure", "success")
| stats count by status
```

**Dynatrace DQL:**
```dql
fetch logs
| fields status = if(level == "ERROR", "failure", "success")
| summarize count(), by:{status}
```

### Pattern 5: Percentile Distribution

**Splunk SPL:**
```spl
index=gofr sourcetype=json
| stats perc50(duration) as p50, perc95(duration) as p95, perc99(duration) as p99
```

**Dynatrace DQL:**
```dql
fetch logs
| summarize p50 = percentile(duration, 50), 
            p95 = percentile(duration, 95), 
            p99 = percentile(duration, 99)
```

## Validation Checklist

Before marking dashboard validation complete:

- [ ] All Splunk dashboards identified and inventoried
- [ ] All SPL queries parsed and field references extracted
- [ ] Field mappings cross-referenced against analyze skill output
- [ ] Breakage risks assessed (green/yellow/red)
- [ ] Required updates documented for each dashboard
- [ ] Dynatrace DQL equivalents generated
- [ ] Dashboard owners notified of required changes
- [ ] High-risk dashboards flagged for manual review
- [ ] Migration checklist provided per dashboard

## Validation Workflow Summary

**Full workflow for validating Splunk dashboards:**

```
1. Identify Splunk application → Validate repository exists
2. Count dashboards/alerts → Assess scope (46 dashboards, 145 alerts)
3. Filter to service (if large app) → Focus validation on relevant objects
4. Parse dashboards → Distinguish metrics (skip) from logs (validate)
5. Expand macros → Get actual SPL queries
6. Extract field references → List all fields used
7. Load field mappings → Get rename/remove decisions from analyze report
8. Validate each query → GREEN/YELLOW/RED risk assessment
9. Parse alerts (savedsearches.conf) → Validate same as dashboards
10. Generate report → Comprehensive with DQL equivalents
11. Communicate scope → "Only 'nobody' shared objects validated"
```

**Time Estimates:**
- Small app (<10 dashboards): 15-30 minutes
- Medium app (10-30 dashboards): 30-60 minutes
- Large app (>30 dashboards): 1-2 hours (recommend service-specific filtering)

## Action Items and Next Steps

**Every validation report should end with clear, actionable next steps:**

```markdown
## Next Steps

### Immediate Actions

- [ ] **Review LOW confidence queries** ({N} queries) - Verify they filter to your service
- [ ] **Check unanalyzed dashboards** ({X} dashboards) - Scan for queries matching your service
- [ ] **Verify dynamic filters** - Confirm `$host$` and similar variables have correct values

### Before Production Deployment

- [ ] **Test in non-production** - Deploy to integration/staging first
- [ ] **Verify queries return data** - Check all dashboard panels after migration
- [ ] **Test DQL equivalents** - Validate Dynatrace queries before using

### Unanalyzed Dashboards

The following {X} dashboards weren't analyzed (generic filenames). 
Check them for queries matching your service:

{List dashboards that were skipped}

**How to check**: Open in Splunk UI, search for: `host={service}*` or `source=/var/log/{service}/*`

### Migration to Dynatrace

- [ ] **Create Dynatrace dashboards** using DQL equivalents above
- [ ] **Run dual ingestion** (Phase 2) to validate both systems show same data
- [ ] **Compare results** between Splunk and Dynatrace
- [ ] **Fix discrepancies** before decommissioning Splunk
```

**END OF REPORT**

## References

- **Splunk Object Backup Repository**: https://github.com/fs-eng/paas-splunk-object-backup
  - Shared objects in `nobody/{app-name}/` directory
  - Dashboards in `data/ui/views/*.xml`
  - Alerts in `savedsearches.conf`
  - Macros in `macros.conf`
- **FamilySearch Observability Standards**: `/home/fransonsr/github/satoris-claude-config/skills/splunk-to-dynatrace/references/familysearch-observability-standards.md`
- **Dynatrace DQL Documentation**: https://docs.dynatrace.com/docs/observe-and-explore/query-data/dynatrace-query-language
- **Splunk SPL Reference**: https://docs.splunk.com/Documentation/Splunk/latest/SearchReference
- **Field Naming Analysis**: Output from `splunk-to-dynatrace:analyze` skill

---

**Remember**: 
- Test in non-production before deploying to production
- Verify LOW confidence queries in actual Splunk
- Check unanalyzed dashboards for service-specific queries
- Test DQL equivalents before using in Dynatrace
