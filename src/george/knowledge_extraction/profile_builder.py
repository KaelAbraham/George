"""
Profile Builder - Creates detailed markdown profiles for each entity
"""
import os
import sys
from pathlib import Path
from typing import Dict, List

# Add parent to path if needed
current_dir = Path(__file__).parent
george_dir = current_dir.parent
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

from llm_integration import GeorgeAI
from knowledge_extraction.entity_extractor import Entity

class ProfileBuilder:
    """Builds detailed profiles for entities using AI analysis."""
    
    def __init__(self, george_ai: GeorgeAI, knowledge_base_path: str):
        """
        Initialize profile builder.
        
        Args:
            george_ai: AI instance for analysis
            knowledge_base_path: Directory to store entity profiles
        """
        self.ai = george_ai
        self.kb_path = Path(knowledge_base_path)
        self.kb_path.mkdir(parents=True, exist_ok=True)
    
    def build_character_profile(self, character_name: str, full_text: str, entity: Entity) -> str:
        """
        COMPREHENSIVE character profile - dedicated read-through ONLY for this character.
        Captures EVERY description, action, and dialogue.
        
        Args:
            character_name: Name of the character
            full_text: Complete manuscript text
            entity: Entity object with initial extraction data
            
        Returns:
            Path to the created markdown file
        """
        print(f"\n📝 Building comprehensive profile for: {character_name}")
        print(f"   Reading entire manuscript looking ONLY for {character_name}...")
        
        # Large chunks for better narrative context
        chunk_size = 10000  # ~5 pages per chunk
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        # Collect ALL information about this character
        observations = []
        
        # Process each chunk - focused ONLY on this character
        for i, chunk in enumerate(chunks):
            if character_name not in chunk:
                continue  # Skip chunks where character doesn't appear
            
            print(f"   📖 Reading section {i+1}/{len(chunks)}...")
            
            # Focused extraction prompt
            prompt = f"""Read this text ONLY looking for information about "{character_name}".

TEXT:
{chunk}

Extract EVERYTHING about {character_name}:

**PHYSICAL DESCRIPTIONS**: What do they look like? (appearance, clothing, features, movements)
**ACTIONS**: What do they DO in this section? (every action, however small)
**DIALOGUE**: What do they SAY? (quote their words)
**THOUGHTS/FEELINGS**: What are they thinking or feeling?
**RELATIONSHIPS**: How do they interact with others?
**CHARACTERIZATION**: What does this reveal about their personality?

Be exhaustive. Capture EVERY detail, even small ones. Quote exact phrases when possible."""
            
            result = self.ai.chat(prompt, project_context="")
            if result['success']:
                observations.append({
                    'section': i+1,
                    'content': result['response']
                })
        
        print(f"   ✅ Collected {len(observations)} sections with {character_name}")
        
        # Now synthesize ALL observations into comprehensive profile
        print(f"   🔄 Synthesizing comprehensive profile...")
        
        all_observations = '\n\n---SECTION---\n\n'.join([obs['content'] for obs in observations])
        
        summary_prompt = f"""Create a comprehensive character profile for "{character_name}" based on ALL these observations:

{all_observations}

Create a well-organized profile with these sections:

## Physical Description
All appearance details, clothing, distinctive features, physical mannerisms

## Personality & Character
Traits revealed through actions and dialogue, values, motivations

## Relationships
Connections with other characters, dynamics, conflicts

## Actions & Key Moments
Major events, decisions, and actions in chronological order

## Dialogue & Voice
Speaking style, notable quotes, communication patterns

## Character Development
Any growth or changes throughout the story

Be thorough and organized. Synthesize information without losing important details."""
        
        result = self.ai.chat(summary_prompt, project_context="")
        final_profile = result['response'] if result['success'] else "Profile generation failed."
        
        # Create markdown file with COMPREHENSIVE information
        profile_md = f"""# Character Profile: {character_name}

**Total Mentions:** {entity.mention_count}
**First Appearance:** Position {entity.first_mention}

---

{final_profile}

---

## Detailed Observations by Section

{all_observations}
"""
        
        # Save to file
        profile_path = self.kb_path / f"character_{character_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        
        print(f"✅ Profile saved: {profile_path}")
        return str(profile_path)
    
    def build_location_profile(self, location_name: str, full_text: str, entity: Entity) -> str:
        """
        COMPREHENSIVE location profile - dedicated read ONLY for this location.
        Captures EVERY description, event, and reference.
        """
        print(f"\n📍 Building comprehensive profile for: {location_name}")
        print(f"   Reading entire manuscript looking ONLY for {location_name}...")
        
        # Large chunks for context
        chunk_size = 10000
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        observations = []
        
        for i, chunk in enumerate(chunks):
            if location_name not in chunk:
                continue
            
            print(f"   📖 Reading section {i+1}/{len(chunks)}...")
            
            prompt = f"""Read this text ONLY looking for information about the location "{location_name}".

TEXT:
{chunk}

Extract EVERYTHING about {location_name}:

**PHYSICAL DESCRIPTION**: What does it look like? (size, layout, features, atmosphere)
**SENSORY DETAILS**: Sights, sounds, smells, temperature, lighting, etc.
**FUNCTION/PURPOSE**: What happens here? What is it used for?
**EVENTS**: What occurs at this location in this section?
**CHARACTERS**: Who is present? Who comes/goes?
**TIME/CONDITION**: Time of day, weather, season, state of the location
**SIGNIFICANCE**: Why is this location important to the story?

Be exhaustive. Capture EVERY detail about this location."""
            
            result = self.ai.chat(prompt, project_context="")
            if result['success']:
                observations.append({
                    'section': i+1,
                    'content': result['response']
                })
        
        print(f"   ✅ Collected {len(observations)} sections mentioning {location_name}")
        print(f"   🔄 Synthesizing comprehensive profile...")
        
        all_observations = '\n\n---SECTION---\n\n'.join([obs['content'] for obs in observations])
        
        summary_prompt = f"""Create a comprehensive location profile for "{location_name}" based on ALL these observations:

{all_observations}

Create a well-organized profile with these sections:

## Physical Description
Complete visual description, layout, size, architectural details

## Sensory Environment
Atmosphere, sounds, smells, lighting, temperature, overall mood

## Purpose & Function
What this location is used for, its role in the story

## Events & Scenes
Major events that occur here, in order

## Associated Characters
Who frequents this location, who owns/controls it

## Significance
Why this location matters to the story

Be thorough and organized."""
        
        result = self.ai.chat(summary_prompt, project_context="")
        final_profile = result['response'] if result['success'] else "Profile generation failed."
        
        # Create comprehensive markdown
        profile_md = f"""# Location Profile: {location_name}

**Total Mentions:** {entity.mention_count}
**First Appearance:** Position {entity.first_mention}

---

{final_profile}

---

## Detailed Observations by Section

{all_observations}
"""
        
        profile_path = self.kb_path / f"location_{location_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        
        print(f"✅ Profile saved: {profile_path}")
        return str(profile_path)
    
    def build_term_profile(self, term_name: str, full_text: str, entity: Entity) -> str:
        """
        COMPREHENSIVE term profile - read for this specific term/concept.
        """
        print(f"\n📚 Building comprehensive profile for: {term_name}")
        print(f"   Reading entire manuscript looking ONLY for {term_name}...")
        
        chunk_size = 10000
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        observations = []
        
        for i, chunk in enumerate(chunks):
            if term_name not in chunk:
                continue
            
            print(f"   📖 Reading section {i+1}/{len(chunks)}...")
            
            prompt = f"""Read this text ONLY looking for the term/concept "{term_name}".

TEXT:
{chunk}

Extract EVERYTHING about {term_name}:

**DEFINITION/NATURE**: What is it? (object, concept, technology, organization, etc.)
**DESCRIPTION**: Physical or conceptual characteristics
**FUNCTION/PURPOSE**: What does it do? What is it used for?
**USAGE**: How is it used in this section?
**SIGNIFICANCE**: Why is it important to the story?
**RELATIONSHIPS**: How does it relate to characters or events?

Capture every detail about this term."""
            
            result = self.ai.chat(prompt, project_context="")
            if result['success']:
                observations.append({
                    'section': i+1,
                    'content': result['response']
                })
        
        print(f"   ✅ Collected {len(observations)} sections mentioning {term_name}")
        print(f"   🔄 Synthesizing comprehensive profile...")
        
        all_observations = '\n\n---SECTION---\n\n'.join([obs['content'] for obs in observations])
        
        summary_prompt = f"""Create a comprehensive profile for "{term_name}" based on ALL these observations:

{all_observations}

Create an organized explanation covering:

## Definition & Nature
What this term represents, its basic nature

## Description
Detailed characteristics (physical if applicable)

## Purpose & Function
What it does, how it's used

## Significance
Role in the story, importance to plot or characters

## Evolution
Any changes or development throughout the story

Be clear and thorough."""
        
        result = self.ai.chat(summary_prompt, project_context="")
        final_profile = result['response'] if result['success'] else "Profile generation failed."
        
        profile_md = f"""# Term Profile: {term_name}

**Total Mentions:** {entity.mention_count}
**First Appearance:** Position {entity.first_mention}

---

{final_profile}

---

## Detailed Observations by Section

{all_observations}
"""
        
        profile_path = self.kb_path / f"term_{term_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        
        print(f"✅ Profile saved: {profile_path}")
        return str(profile_path)
