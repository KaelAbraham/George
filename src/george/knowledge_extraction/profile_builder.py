"""Profile Builder - Creates detailed markdown profiles for each entity."""
import logging
from pathlib import Path
from typing import List

from ..llm_integration import GeorgeAI
from .entity_extractor import Entity

logger = logging.getLogger(__name__)

class ProfileBuilder:
    """Builds detailed profiles for entities using a dedicated AI client."""
    
    def __init__(self, ai_client: GeorgeAI, knowledge_base_path: str):
        """
        Initialize profile builder.
        
        Args:
            ai_client: A direct CloudAPIClient instance (e.g., Gemini 2.5 Pro) for analysis.
            knowledge_base_path: Directory to store entity profiles.
        """
        self.ai = ai_client
        self.kb_path = Path(knowledge_base_path)
        self.kb_path.mkdir(parents=True, exist_ok=True)
    
    def _safe_generate(self, prompt: str, **kwargs) -> str:
        """Call the AI client, returning ``None`` instead of raising on failure."""
        try:
            return self.ai.generate_response(prompt, **kwargs)
        except Exception as exc:  # noqa: BLE001 - surface all downstream errors uniformly
            logger.warning("AI generation failed: %s", exc)
            return None

    def _fallback_detail_snippets(self, entity: Entity, limit: int = 5) -> List[str]:
        """Generate simple bullet snippets from cached entity contexts."""
        snippets = []
        for ctx in entity.contexts[:limit]:
            cleaned = ctx.strip().replace('\n', ' ')
            if cleaned:
                snippets.append(cleaned)
        return snippets

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
        
        # Chunk the text to find all mentions
        chunk_size = 3000
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        character_data = {
            'name': character_name,
            'appearances': [],
        }
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            if character_name not in chunk:
                continue
            
            print(f"  Analyzing chunk {i+1}/{len(chunks)} for {character_name}...")
            
            prompt = f"""Analyze this text excerpt for information about the character "{character_name}".

---TEXT---
{chunk}
---END TEXT---

List only the facts present in this excerpt regarding "{character_name}":
1. Physical descriptions (appearance, clothing, etc.)
2. Personality traits shown through actions or dialogue
3. Relationships with other characters
4. Key actions or events
5. Notable dialogue

Be BRIEF and FACTUAL. Only list what's explicitly shown."""
            
            response = self._safe_generate(prompt, temperature=0.2)
            if response:
                character_data['appearances'].append({'chunk': i, 'details': response})
        
        # Generate final summary profile
        all_details = '\n\n'.join([app['details'] for app in character_data['appearances']])

        detail_snippets = self._fallback_detail_snippets(entity)

        if not all_details.strip():
            if detail_snippets:
                all_details = '\n'.join(f"- {snippet}" for snippet in detail_snippets)
            else:
                all_details = "No additional AI-generated details are available at this time."

        summary_prompt = f"""Create a comprehensive character profile for "{character_name}" based on these extracted details:

{all_details}

Create a structured profile with sections:
- Physical Description
- Personality
- Relationships
- Key Moments/Actions
- Character Arc (if any development is shown)

Be concise but complete, based ONLY on the information provided."""

        final_profile = self._safe_generate(summary_prompt, temperature=0.5)

        if not final_profile:
            bullet_lines = [
                f"- Mention Count: {entity.mention_count}",
                f"- First Mention Position: {entity.first_mention}",
            ]
            if detail_snippets:
                bullet_lines.append("- Sample Mentions:")
                bullet_lines.extend(f"  - {snippet}" for snippet in detail_snippets)
            else:
                bullet_lines.append("- No additional descriptive details captured.")
            final_profile = "\n".join(bullet_lines)
            logger.info(
                "Generated fallback profile summary for %s due to AI errors.",
                character_name,
            )
        
        # Create markdown file
        profile_md = f"""# Character Profile: {character_name}

**Mention Count:** {entity.mention_count}
**First Appearance:** Character position {entity.first_mention}

## Profile

{final_profile}

## Raw Mentions

{all_details}
"""
        
        profile_path = self.kb_path / f"character_{character_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        
        print(f"[OK] Profile saved: {profile_path}")
        return str(profile_path)
    
    def build_location_profile(self, location_name: str, full_text: str, entity: Entity) -> str:
        """Build a detailed location profile."""
        # This method would be structured similarly to build_character_profile
        # For brevity, we'll keep it simple for now
        profile_md = f"# Location Profile: {location_name}\n\n**Mentions:** {entity.mention_count}"
        profile_path = self.kb_path / f"location_{location_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        return str(profile_path)
    
    def build_term_profile(self, term_name: str, full_text: str, entity: Entity) -> str:
        """Build a profile for unique terms/concepts."""
        # This method would be structured similarly to build_character_profile
        profile_md = f"# Term Profile: {term_name}\n\n**Mentions:** {entity.mention_count}"
        profile_path = self.kb_path / f"term_{term_name.replace(' ', '_')}.md"
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        return str(profile_path)
