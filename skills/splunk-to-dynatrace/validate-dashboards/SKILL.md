---
name: splunk-to-dynatrace:validate-dashboards
description: Validates Splunk dashboards work with structured JSON logging and generates Dynatrace DQL equivalents. Parses SPL queries, identifies field references, validates against structured field mappings, and provides migration guidance. Use this skill when migrating dashboards from Splunk to Dynatrace or validating field name changes.
---

# Validate Dashboards Skill

Validates that Splunk dashboards will continue working after converting to structured JSON logging, and generates equivalent Dynatrace DQL queries for migration.

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

## Skill Workflow

### Step 1: Locate Dashboard Definitions

Identify Splunk dashboards to validate:

1. **Ask user for dashboard locations**:
   - Splunk export files (JSON/XML)
   - Confluence documentation with embedded queries
   - Git repository with dashboard definitions
   - Direct SPL query strings

2. **Scan for dashboard files**:
   - `.json` (JSON dashboard exports)
   - `.xml` (Simple XML dashboards)
   - `.conf` (savedsearches.conf for alerts)

3. **Read dashboard content**:
   - Parse structure (panels, queries, visualizations)
   - Extract all SPL queries

### Step 2: Parse SPL Queries

For each dashboard query:

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

### Step 3: Load Field Mapping Context

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

### Step 4: Validate Each Dashboard

For each dashboard and query:

1. **Check field existence**:
   - Does each referenced field exist in new structured format?
   - If renamed, is mapping documented?

2. **Assess breakage risk**:
   - ✅ **No Risk**: Field preserved with same name
   - ⚠️ **Low Risk**: Field renamed, dashboard needs simple find/replace
   - ❌ **High Risk**: Field removed, query logic needs rework

3. **Generate required updates**:
   - Find/replace operations for renamed fields
   - Query rewrite suggestions for removed fields
   - Equivalent Dynatrace DQL query

### Step 5: Generate Validation Report

Create comprehensive report with:

- Dashboard inventory (name, owner, panels)
- Field reference analysis per dashboard
- Breakage risk assessment (green/yellow/red)
- Required updates for each dashboard
- Dynatrace DQL equivalents

### Step 6: Generate Dynatrace Migration Guide

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

## Best Practices

### 1. Validate Before Deploying

Don't deploy structured logging without validating dashboards first:

1. Run validation skill
2. Review report with dashboard owners
3. Update dashboards preemptively
4. Test with sample JSON data if possible

### 2. Communicate Breaking Changes

If field removed (high risk), communicate clearly:

- **What changed**: Field X removed per observability standards
- **Why changed**: Reason (PII, auto-captured, etc.)
- **Alternative**: Use field Y instead
- **Impact**: Dashboard shows different data or breaks

### 3. Maintain Dashboard Inventory

Keep dashboard inventory up to date:

- Dashboard name and owner
- Last updated date
- Dependencies on specific fields
- Migration status (updated, validated, migrated to Dynatrace)

### 4. Use Hybrid Naming During Migration

If field naming creates dashboard pain, consider hybrid approach (Option 3):

**Log both old and new field names temporarily:**
```java
logger.atInfo()
    .addKeyValue("ordinanceType", type)      // Old name (Splunk dashboards)
    .addKeyValue("ordinance.type", type)     // New name (Dynatrace)
    .log("Processing ordinance");
```

**Remove old names after dashboards updated.**

### 5. Create Dynatrace Dashboards Early

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

## References

- **FamilySearch Observability Standards**: `/home/fransonsr/github/satoris-claude-config/skills/splunk-to-dynatrace/references/familysearch-observability-standards.md`
- **Dynatrace DQL Documentation**: https://docs.dynatrace.com/docs/observe-and-explore/query-data/dynatrace-query-language
- **Splunk SPL Reference**: https://docs.splunk.com/Documentation/Splunk/latest/SearchReference
- **Field Naming Analysis**: Output from `splunk-to-dynatrace:analyze` skill

---

**Remember**: Dashboard validation is critical for preventing operational blind spots during migration. Validate early, communicate clearly, and migrate dashboards incrementally.
