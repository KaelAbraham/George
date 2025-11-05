# Automatic Knowledge Base Generator

## Overview
The Knowledge Extraction system performs **comprehensive, dedicated analysis** of your manuscript. It takes time during upload but creates thorough, accurate profiles that enable fast, intelligent queries.

---

## The 3-Step Process

### **STEP 1: IDENTIFICATION** 
**"Read to identify each character, setting, and anything with a proper name"**

- **What it does:** AI reads the ENTIRE manuscript in large chunks (20,000 characters each)
- **Goal:** Identify EVERY character, location, and significant term
- **Output:** Complete list of all entities found
- **Time:** ~2-5 minutes depending on manuscript length

**Example Output:**
```
✅ STEP 1 COMPLETE - Identified:
   • 7 Characters
   • 3 Locations
   • 12 Terms/Concepts
   Total: 22 entities
```

---

### **STEP 2: PROFILE CREATION**
**"Make a .md file for each element"**

- **What it does:** Creates a markdown file for each identified entity
- **Location:** `data/uploads/projects/{project_id}/knowledge_base/`
- **Files created:**
  - `character_Name.md`
  - `location_Name.md`
  - `term_Name.md`

---

### **STEP 3: DEEP ANALYSIS**
**"Read the manuscript only looking for one element and noting everything about it"**

- **What it does:** For EACH entity, re-reads the ENTIRE manuscript looking ONLY for that entity
- **Chunk size:** 10,000 characters (~5 pages) for maximum context
- **Extraction:** Captures EVERY description, action, dialogue, and reference

**For Characters:**
- Physical descriptions (appearance, clothing, mannerisms)
- Every action they take
- All dialogue (quoted exactly)
- Thoughts and feelings
- Relationships with others
- Character development

**For Locations:**
- Physical description and layout
- Sensory details (sights, sounds, atmosphere)
- Events that occur there
- Associated characters
- Time/weather/condition
- Significance to story

**For Terms:**
- Definition and nature
- Physical/conceptual characteristics
- Function and purpose
- Usage examples
- Relationships to characters/events
- Evolution throughout story

---

## Profile Structure

Each `.md` file contains:

1. **Comprehensive Summary** - AI synthesis of all observations
2. **Detailed Observations** - Raw findings from each section of the manuscript
3. **Metadata** - Total mentions, first appearance position

**Example Character Profile:**
```markdown
# Character Profile: granGillan

**Total Mentions:** 45
**First Appearance:** Position 1234

---

## Physical Description
[Synthesized from ALL observations]

## Personality & Character
[Traits revealed throughout story]

## Actions & Key Moments
[Chronological list of everything they do]

## Dialogue & Voice
[Speaking style with quotes]

---

## Detailed Observations by Section
[Raw observations from each chunk analyzed]
```

---

## Why This Takes Time

**Upload Processing Time:** 10-30 minutes depending on manuscript length

**Why it's worth it:**
- ✅ **Accuracy:** Every detail captured, nothing missed
- ✅ **Completeness:** Analyzes entire manuscript, not just excerpts
- ✅ **Speed:** Queries are instant because profiles are pre-built
- ✅ **Intelligence:** AI understands relationships and context
- ✅ **Scalability:** Works with manuscripts of ANY size

---

## Technical Details

### Chunk Sizes
- **Entity Identification:** 20,000 characters (covers ~10 pages per chunk)
- **Profile Building:** 10,000 characters (~5 pages per chunk for context)

### AI Model
- **Gemini 2.0 Flash** via Google Cloud API
- Comprehensive prompts for thorough extraction
- Context-aware analysis

### Storage
- Profiles stored in project-specific knowledge base folder
- Markdown format for readability and portability
- Can be edited manually if needed

---

## Using the Knowledge Base

Once extraction is complete, you can ask:
- **"What does [character] look like?"** - Gets complete physical description
- **"What happens at [location]?"** - Lists all events at that location
- **"Who are the main characters?"** - Identifies characters by mention count
- **"Describe the setting"** - Comprehensive location information

The AI automatically:
1. Analyzes your query
2. Identifies relevant entities
3. Loads their profiles
4. Synthesizes an accurate answer

---

## Progress Indicators

During upload, you'll see:
- **Orange border:** "Progress: XX% - Please wait..."
- **Processing steps:** Real-time updates in console
- **Green border:** "🎉 READY! Extracted X characters, Y locations, Z terms"
- **Final message:** "✅ READY FOR QUERIES!"

---

## Example Console Output

```
================================================================================
🚀 AUTOMATIC KNOWLEDGE BASE GENERATOR
   Manuscript: EAWAN.txt
================================================================================

================================================================================
STEP 1: IDENTIFICATION - Reading manuscript to identify entities
================================================================================
🔍 Step 1: Comprehensive Entity Identification
   Reading manuscript to identify ALL characters, settings, and proper names...
   Analyzing chunk 1/2...
   Analyzing chunk 2/2...

✅ STEP 1 COMPLETE - Identified:
   • 7 Characters
   • 3 Locations
   • 12 Terms/Concepts
   Total: 22 entities

================================================================================
STEP 2: PROFILE CREATION - Creating .md file for each entity
================================================================================

================================================================================
STEP 3: DEEP ANALYSIS - Reading manuscript for each entity
================================================================================

[1/22] Processing character: granGillan

📝 Building comprehensive profile for: granGillan
   Reading entire manuscript looking ONLY for granGillan...
   📖 Reading section 1/4...
   📖 Reading section 2/4...
   📖 Reading section 3/4...
   📖 Reading section 4/4...
   ✅ Collected 4 sections with granGillan
   🔄 Synthesizing comprehensive profile...
✅ Profile saved: character_granGillan.md

[2/22] Processing character: Aiden
...
```

---

## Comparison: Old vs New

### Old System (Quick but Incomplete)
- ❌ Regex-based entity detection (missed proper names)
- ❌ Small chunks (3000 chars = fragmented context)
- ❌ Quick analysis (missed details)
- ⚠️ Result: Fast but inaccurate

### New System (Thorough and Complete)
- ✅ AI-powered entity identification (comprehensive)
- ✅ Large chunks (10,000 chars = full context)
- ✅ Dedicated read per entity (captures everything)
- ✅ Result: Takes time but **highly accurate**

---

## Future Enhancements

Potential additions:
- **Scene tracking:** Break manuscript into scenes with timeline
- **Relationship maps:** Visual graph of character connections
- **Theme extraction:** Identify recurring motifs and themes
- **Sentiment analysis:** Track emotional arcs
- **Export options:** PDF reports, JSON data export
