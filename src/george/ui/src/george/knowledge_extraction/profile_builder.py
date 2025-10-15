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
        Build a detailed character profile by analyzing the full manuscript.
        
        Args:
            character_name: Name of the character
            full_text: Complete manuscript text
            entity: Entity object with initial extraction data
            
        Returns:
            Path to the created markdown file
        """
        print(f"[BUILD] Building profile for character: {character_name}")
        
        # Chunk the text (process in 3000 char chunks to find all mentions)
        chunk_size = 3000
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        character_data = {
            'name': character_name,
            'appearances': [],
            'physical_description': [],
            'personality_traits': [],
            'relationships': [],
            'actions': [],
            'dialogue_samples': []
        }
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            if character_name not in chunk:
                continue  # Skip chunks where character doesn't appear
            
            print(f"  Analyzing chunk {i+1}/{len(chunks)}...")
            
            # Ask AI to extract details from this chunk
            prompt = f"""Analyze this text excerpt for information about the character "{character_name}".

---TEXT---
{chunk}
---END TEXT---

List only the facts present in this excerpt:
1. Physical descriptions (appearance, clothing, etc.)
2. Personality traits shown through actions or dialogue
3. Relationships with other characters
4. Key actions or events
5. Notable dialogue

Be BRIEF and FACTUAL. Only list what's explicitly shown."""
            
            response = self.ai.generate_response(prompt, temperature=0.2)
            if response:
                character_data['appearances'].append({
                    'chunk': i,
                    'details': response
                })
        
        # Generate final summary profile
        all_details = '\n\n'.join([app['details'] for app in character_data['appearances']])
        
        summary_prompt = f"""Create a comprehensive character profile for "{character_name}" based on these extracted details:

{all_details}

Create a structured profile with sections:
- Physical Description
- Personality
- Relationships
- Key Moments/Actions
- Character Arc (if any development is shown)

Be concise but complete."""
        
        final_profile = self.ai.generate_response(summary_prompt, temperature=0.5)
        if not final_profile:
            final_profile = "Profile generation failed."
        
        # Create markdown file
        profile_md = f"""# Character Profile: {character_name}

**Mention Count:** {entity.mention_count}
**First Appearance:** Character position {entity.first_mention}

## Profile

{final_profile}

## Raw Mentions

{all_details}
"""
        
        # Save to file
        profile_path = self.kb_path / f"character_{character_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        
        print(f"[OK] Profile saved: {profile_path}")
        return str(profile_path)
    
    def build_location_profile(self, location_name: str, full_text: str, entity: Entity) -> str:
        """Build a detailed location profile."""
        print(f"📍 Building profile for location: {location_name}")
        
        # Similar chunking approach
        chunk_size = 3000
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        location_details = []
        
        for i, chunk in enumerate(chunks):
            if location_name not in chunk:
                continue
            
            print(f"  Analyzing chunk {i+1}/{len(chunks)}...")
            
            prompt = f"""Analyze this text for information about the location "{location_name}".

---TEXT---
{chunk}
---END TEXT---

List only what's explicitly described:
1. Physical description (size, appearance, atmosphere)
2. Purpose/function of this location
3. Events that happen here
4. Characters associated with this location

Be BRIEF and FACTUAL."""
            
            response = self.ai.generate_response(prompt, temperature=0.2)
            if response:
                location_details.append(response)
        
        # Generate summary
        all_details = '\n\n'.join(location_details)
        
        summary_prompt = f"""Create a location profile for "{location_name}" based on these details:

{all_details}

Include:
- Physical Description
- Purpose/Significance
- Notable Events
- Atmosphere/Mood"""
        
        final_profile = self.ai.generate_response(summary_prompt, temperature=0.5)
        if not final_profile:
            final_profile = "Profile generation failed."
        
        # Create markdown
        profile_md = f"""# Location Profile: {location_name}

**Mentions:** {entity.mention_count}

## Description

{final_profile}

## Details from Text

{all_details}
"""
        
        profile_path = self.kb_path / f"location_{location_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        
        print(f"[OK] Profile saved: {profile_path}")
        return str(profile_path)
    
    def build_term_profile(self, term_name: str, full_text: str, entity: Entity) -> str:
        """Build a profile for unique terms/concepts."""
        print(f"[BUILD] Building profile for term: {term_name}")
        
        # For terms, extract all contexts where it appears
        contexts = entity.contexts[:10]  # Limit to first 10 mentions
        
        prompt = f"""Analyze this term "{term_name}" based on how it's used in context:

Contexts:
{chr(10).join(contexts)}

Describe:
1. What this term refers to (object, concept, technology, etc.)
2. Its significance in the story
3. How it's used

Be BRIEF."""
        
        description = self.ai.generate_response(prompt, temperature=0.3)
        if not description:
            description = "Analysis failed."
        
        profile_md = f"""# Term: {term_name}

**Mentions:** {entity.mention_count}

## Description

{description}

## Example Contexts

{chr(10).join([f"- {ctx[:200]}..." for ctx in contexts])}
"""
        
        profile_path = self.kb_path / f"term_{term_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        
        print(f"[OK] Profile saved: {profile_path}")
        return str(profile_path)
