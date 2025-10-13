# Profile Editing Guide

## Overview
You can now **edit knowledge base profiles directly through chat** using natural language commands. The AI will intelligently update the markdown files based on your instructions.

---

## Edit Commands

### 1. **UPDATE / CORRECT**
Fix incorrect information or update existing details.

**Examples:**
- `Update Edie Ann: she has brown eyes, not blue`
- `Correct Hugh's profile: he's 45 years old, not 35`
- `Fix Linda: she's from Mars, not Earth`
- `Change granGillan: add that he has a gray beard`

**What it does:**
- Finds the existing information
- Replaces it with the corrected version
- Maintains all other content

---

### 2. **ADD TO**
Add new information to an existing profile.

**Examples:**
- `Add to Edie Ann's profile: she loves building robots`
- `Add to Hugh: he has a PhD in physics`
- `Add to Workshop: it has zero-gravity controls`

**What it does:**
- Keeps all existing content
- Adds new information to the appropriate section
- Creates new sections if needed

---

### 3. **REMOVE FROM**
Delete incorrect or outdated information.

**Examples:**
- `Remove from Linda: the part about her being an engineer`
- `Remove from Akkadia: delete the mention of blue skies`
- `Remove from Richards: his title as Captain`

**What it does:**
- Identifies and removes only the specified information
- Keeps everything else intact
- Removes empty sections if needed

---

### 4. **MERGE**
Combine two profiles that describe the same entity.

**Examples:**
- `Merge Carroll and Dad`
- `Merge "The Workshop" and "Workshop"`
- `Merge granGillan and Grandma Grace`

**What it does:**
- Combines all information from both profiles
- Uses the more complete name as the main title
- Resolves contradictions intelligently
- Deletes the duplicate profile

---

## How It Works

### Backend Process:

1. **Detection:** The system detects edit commands using regex patterns
   ```
   "Update X: Y"
   "Add to X: Y"
   "Remove from X: Y"
   "Merge X and Y"
   ```

2. **File Lookup:** Finds the correct `.md` file (case-insensitive)
   - Searches for: `character_Name.md`, `location_Name.md`, `term_Name.md`
   - Handles variations: "Edie Ann" matches `character_Edie_Ann.md`

3. **AI Editing:** Sends current profile + instruction to AI
   - AI reads the entire profile
   - Makes intelligent edits following specific rules
   - Returns the complete updated profile

4. **File Update:** Saves the new version
   - Overwrites the markdown file
   - Maintains structure and formatting

---

## Command Patterns

The system recognizes these patterns:

```
UPDATE:
- update [entity]: [instruction]
- correct [entity]: [instruction]
- fix [entity]: [instruction]
- change [entity]: [instruction]

ADD:
- add to [entity]: [instruction]
- add to [entity]'s profile: [instruction]

REMOVE:
- remove from [entity]: [instruction]
- delete from [entity]: [instruction]

MERGE:
- merge [entity1] and [entity2]
- merge [entity1] with [entity2]
```

**Case Insensitive:** All commands work regardless of capitalization

---

## AI Editing Rules

When the AI edits profiles, it follows these rules:

### Update/Correct:
1. Keep markdown structure (headers, bold text, etc.)
2. Keep metadata section (mentions, first appearance)
3. Update ONLY the relevant sections
4. Maintain professional, factual tone
5. Don't remove other information

### Add:
1. Keep all existing content
2. Add to appropriate section (Physical Description, Personality, etc.)
3. Create new sections if needed
4. Integrate smoothly with existing text

### Remove:
1. Remove ONLY specified information
2. Keep everything else intact
3. Remove section headers if section becomes empty
4. Don't leave awkward gaps

### Merge:
1. Use more complete/formal name as title
2. Combine sections intelligently
3. Don't duplicate information
4. Resolve contradictions (prefer more specific)
5. Create comprehensive single profile

---

## Response Messages

After executing an edit, you'll see:

**Success:**
```
✅ Updated profile for 'Edie Ann'
✅ Added information to 'Hugh' profile
✅ Removed information from 'Linda' profile
✅ Merged 'Carroll' into 'Dad'. Deleted duplicate profile.
```

**Failure:**
```
❌ Edit failed: Could not find profile for 'Unknown'
❌ Edit failed: Error reading profile
❌ Edit failed: AI edit failed
```

---

## Examples

### Scenario 1: Fix Incorrect Eye Color

**You notice the profile says Edie Ann has blue eyes, but the manuscript says brown.**

Command:
```
Update Edie Ann: her eyes are brown, not blue
```

Result:
- Profile's Physical Description section updated
- "blue eyes" replaced with "brown eyes"
- All other details unchanged

---

### Scenario 2: Add Missing Profession

**Hugh's profile doesn't mention he's an engineer.**

Command:
```
Add to Hugh's profile: he's a skilled aerospace engineer
```

Result:
- New information added to Personality/Character section (or new section created)
- Existing content preserved
- Smooth integration with existing text

---

### Scenario 3: Merge Duplicate Characters

**"Dad" and "Carroll" are the same person but have separate profiles.**

Command:
```
Merge Dad and Carroll
```

Result:
- All information from both profiles combined
- Saved to one comprehensive profile
- Duplicate file deleted
- References to both names in profile

---

### Scenario 4: Remove Wrong Location

**Linda's profile incorrectly says she's from Earth.**

Command:
```
Remove from Linda: the part about her being from Earth
```

Result:
- Earth reference removed
- All other location info intact
- Section reformatted if needed

---

## Technical Details

### File Structure:
```
knowledge_base/
├── character_Edie_Ann.md
├── character_Hugh_Sinclair.md
├── location_Akkadia.md
└── term_ScioNetics.md
```

### Profile Editor Architecture:
```python
ProfileEditor
├── detect_edit_command()    # Pattern matching
├── find_profile_file()      # File lookup
├── update_profile()         # Update edits
├── add_to_profile()         # Add edits
├── remove_from_profile()    # Remove edits
├── merge_profiles()         # Merge edits
└── execute_edit()           # Main executor
```

### Integration:
```
User Input
    ↓
Flask /api/chat endpoint
    ↓
KnowledgeExtractor.edit_profile()
    ↓
ProfileEditor.detect_edit_command()
    ↓
ProfileEditor.execute_edit()
    ↓
AI processes instruction
    ↓
Updated .md file saved
    ↓
Success message returned
```

---

## Tips for Best Results

1. **Be Specific:** 
   - ✅ "Update Edie Ann: she has curly brown hair"
   - ❌ "Update Edie Ann: change her hair"

2. **Use Full Names:**
   - ✅ "Add to Hugh Sinclair: ..."
   - ⚠️ "Add to Hugh: ..." (works but less precise)

3. **One Edit at a Time:**
   - ✅ Make separate commands for different entities
   - ⚠️ Combining multiple edits in one command may be unclear

4. **Check Entity Names:**
   - Use "List the characters" to see available entities
   - Match names as they appear in the knowledge base

5. **After Editing:**
   - Ask a query to verify the change
   - "What color are Edie Ann's eyes?" should now be correct

---

## Troubleshooting

**"Could not find profile"**
- Check spelling of entity name
- Use "List the characters/locations/terms" to see exact names
- Try variations: "Edie Ann" vs "EdieAnn"

**"Not recognized as an edit command"**
- Ensure you use a recognized pattern (Update, Add to, Remove from, Merge)
- Check syntax: "Update [name]: [instruction]"

**Edit executed but seems wrong**
- The AI interpreted your instruction differently
- Use "Update [name]:" again with more specific wording
- You can always re-edit the same profile

---

## Future Enhancements

Potential additions:
- **Undo command:** Revert last edit
- **View profile:** Show current profile in chat
- **Bulk edits:** Update multiple entities at once
- **Edit history:** Track all changes made
- **Validation:** Verify edits against source text
