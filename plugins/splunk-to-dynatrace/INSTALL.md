# Installation Guide

## Prerequisites

- Claude Code CLI (`claude` command) or Desktop App installed
- Access to FamilySearch internal repositories (if applicable)
- Basic familiarity with Claude Code plugins

## Installation Methods

### Method 1: Install from Distribution Archive (Recommended)

1. **Download the latest release**:
   ```bash
   # Download tar.gz or zip from distribution channel
   wget https://path-to-releases/splunk-to-dynatrace-1.0.0.tar.gz
   
   # Or copy from shared location
   cp /shared/plugins/splunk-to-dynatrace-1.0.0.tar.gz .
   ```

2. **Extract the archive**:
   ```bash
   # For tar.gz
   tar -xzf splunk-to-dynatrace-1.0.0.tar.gz
   
   # For zip
   unzip splunk-to-dynatrace-1.0.0.zip
   ```

3. **Install the plugin**:
   ```bash
   # Move to Claude plugins directory
   mv splunk-to-dynatrace ~/.claude/plugins/
   
   # Or use Claude Code CLI (if supported)
   claude plugin install ./splunk-to-dynatrace
   ```

4. **Verify installation**:
   ```bash
   # In Claude Code session
   /splunk-to-dynatrace:analyze --help
   ```

---

### Method 2: Install from Source (Development)

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd satoris-claude-config/plugins/splunk-to-dynatrace
   ```

2. **Install dependencies**:
   ```bash
   # Python dependencies for bundled scripts
   pip3 install --user jedi-language-server
   
   # NEW v2.0.0: JPype for JavaParser transformer (convert-logs skill)
   sudo apt-get install python3-jpype  # Ubuntu/Debian (recommended)
   # Or: pip3 install --user jpype1  # User install (alternative)
   ```

3. **Symlink to plugins directory**:
   ```bash
   ln -s "$(pwd)" ~/.claude/plugins/splunk-to-dynatrace
   ```

4. **Verify installation**:
   ```bash
   # In Claude Code session
   /splunk-to-dynatrace:choose-approach
   ```

---

## Verification

After installation, verify the plugin is loaded:

### Check Available Skills

In a Claude Code session:

```
List available skills from splunk-to-dynatrace plugin
```

You should see:
- `/splunk-to-dynatrace:analyze`
- `/splunk-to-dynatrace:choose-approach`
- `/splunk-to-dynatrace:convert-logs`
- `/splunk-to-dynatrace:migrate`
- `/splunk-to-dynatrace:setup-logback`
- `/splunk-to-dynatrace:validate-dashboards`

### Run a Test Skill

Test the choose-approach skill (quickest to verify):

```bash
# In Claude Code session
/splunk-to-dynatrace:choose-approach
```

Expected: Interactive questionnaire starts asking about dashboards, urgency, etc.

---

## Troubleshooting

### Plugin Not Found

**Problem**: Claude Code says "skill not found" when invoking `/splunk-to-dynatrace:*`

**Solutions**:

1. **Check plugin directory**:
   ```bash
   ls -la ~/.claude/plugins/splunk-to-dynatrace
   ```
   Should show plugin files.

2. **Verify plugin.json exists**:
   ```bash
   cat ~/.claude/plugins/splunk-to-dynatrace/.claude-plugin/plugin.json
   ```

3. **Restart Claude Code** (if using Desktop App)

4. **Check plugin permissions**:
   ```bash
   chmod -R u+rw ~/.claude/plugins/splunk-to-dynatrace
   ```

---

### Python Script Errors

**Problem**: `lsp_inventory.py` fails with import errors

**Solutions**:

1. **Install jedi-language-server**:
   ```bash
   pip3 install --user jedi-language-server
   ```

2. **Verify Python version**:
   ```bash
   python3 --version  # Should be 3.8+
   ```

3. **Check script executability**:
   ```bash
   chmod +x ~/.claude/plugins/splunk-to-dynatrace/skills/analyze/scripts/lsp_inventory.py
   ```

---

### JavaParser Transformer Errors (v2.0.0+)

**Problem**: `transform_jpype.py` fails with JPype errors (convert-logs skill)

**Solutions**:

1. **Install JPype** (Ubuntu/Debian):
   ```bash
   sudo apt-get install python3-jpype
   ```

2. **Alternative: Install via pip** (if system package not available):
   ```bash
   # User install
   pip3 install --user jpype1
   
   # Or virtual environment (recommended for development)
   python3 -m venv venv
   source venv/bin/activate
   pip install jpype1
   ```

3. **Verify JPype installation**:
   ```bash
   python3 -c "import jpype; print(jpype.__version__)"
   # Should print version >= 1.4.1
   ```

4. **Check Java installation** (required for JVM):
   ```bash
   java -version
   # Should be Java 11+
   ```

5. **JavaParser JAR auto-download**:
   - First run of `transform_jpype.py` will auto-download JavaParser JAR to `~/.cache/javaparser/`
   - If download fails, manually download from: https://repo1.maven.org/maven2/com/github/javaparser/javaparser-core/3.25.8/javaparser-core-3.25.8.jar
   - Place in: `~/.cache/javaparser/javaparser-core-3.25.8.jar`

---

### Skill Triggers But Fails

**Problem**: Skill starts but encounters errors during execution

**Debugging Steps**:

1. **Check Claude Code logs** (if available)
   
2. **Run skill with simpler input** (eliminate complex edge cases)

3. **Verify required files**:
   ```bash
   # Observability standards reference
   cat ~/.claude/plugins/splunk-to-dynatrace/references/familysearch-observability-standards.md
   ```

4. **Check for workspace conflicts**:
   ```bash
   # Ensure no stale workspace artifacts
   rm -rf ~/.claude/plugins/splunk-to-dynatrace/skills/*/workspace
   ```

---

## Updating the Plugin

### Update from Distribution

1. **Download new version**:
   ```bash
   wget https://path-to-releases/splunk-to-dynatrace-1.1.0.tar.gz
   ```

2. **Remove old version**:
   ```bash
   rm -rf ~/.claude/plugins/splunk-to-dynatrace
   ```

3. **Install new version** (same steps as initial install)

4. **Verify update**:
   ```bash
   cat ~/.claude/plugins/splunk-to-dynatrace/.claude-plugin/plugin.json | grep version
   ```

### Update from Source

```bash
cd ~/.claude/plugins/splunk-to-dynatrace
git pull origin main
```

---

## Uninstallation

To remove the plugin:

```bash
rm -rf ~/.claude/plugins/splunk-to-dynatrace
```

Your project-specific data (`.claude/workspace/`) in your repositories is **not** affected.

---

## Configuration

### Optional: Custom References

If your organization has custom observability standards:

1. Replace or supplement the reference file:
   ```bash
   cp your-standards.md ~/.claude/plugins/splunk-to-dynatrace/references/
   ```

2. Update skills to reference your custom file (edit SKILL.md)

---

## Getting Help

**Documentation**:
- [README.md](README.md) - Plugin overview and usage
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development guide
- [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) - Feature roadmap

**Support**:
- FamilySearch Engineering - SATORIS Team
- Email: fransonsr@familysearch.org
- Slack: #dynatrace-migration (if available)

**Report Issues**:
- Describe the problem clearly
- Include skill name and input
- Attach relevant error messages
- Provide context (codebase size, Java version, etc.)

---

## Next Steps

After successful installation:

1. **Start with choose-approach skill**: Get personalized migration plan
   ```
   /splunk-to-dynatrace:choose-approach
   ```

2. **Or run analysis**: Understand your current logging state
   ```
   /splunk-to-dynatrace:analyze
   ```

3. **Review documentation**: [README.md](README.md) for complete usage guide

4. **Join community**: Share feedback and learnings with other teams

Happy migrating! 🚀
