"""
Profile Editor - Allows AI-guided editing of knowledge base profiles
"""
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
import re

# Add parent to path if needed
current_dir = Path(__file__).parent
george_dir = current_dir.parent
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

from llm_integration import GeorgeAI

class ProfileEditor:
    """Edit knowledge base profiles based on user instructions."""
    
    def __init__(self, george_ai: GeorgeAI, knowledge_base_path: str):
        """
        Initialize profile editor.
        
        Args:
            george_ai: AI instance for intelligent editing
            knowledge_base_path: Directory where entity profiles are stored
        """
        self.ai = george_ai
        self.kb_path = Path(knowledge_base_path)
    
    def detect_edit_command(self, query: str) -> Optional[Dict]:
        """
        Detect if query is an edit command.
        
        Returns dict with:
        - command_type: 'update', 'add', 'remove', 'merge', 'correct'
        - entity: target entity name
        - instruction: what to change
        
        Returns None if not an edit command.
        """
        query_lower = query.lower()
        
        # Edit command patterns
        edit_patterns = [
            (r'update\s+([^:\'\"]+)[\:\s]+(.+)', 'update'),
            (r'correct\s+([^:\'\"]+)[\:\s]+(.+)', 'correct'),
            (r'add\s+to\s+([^:\'\"]+)[\:\s]+(.+)', 'add'),
            (r'remove\s+from\s+([^:\'\"]+)[\:\s]+(.+)', 'remove'),
            (r'fix\s+([^:\'\"]+)[\:\s]+(.+)', 'correct'),
            (r'change\s+([^:\'\"]+)[\:\s]+(.+)', 'update'),
            (r'merge\s+([^\'\"]+)\s+(?:and|with)\s+([^\'\"]+)', 'merge'),
        ]
        
        for pattern, cmd_type in edit_patterns:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                if cmd_type == 'merge':
                    return {
                        'command_type': 'merge',
                        'entity': match.group(1).strip(),
                        'merge_with': match.group(2).strip(),
                        'instruction': query
                    }
                else:
                    return {
                        'command_type': cmd_type,
                        'entity': match.group(1).strip(),
                        'instruction': match.group(2).strip()
                    }
        
        return None
    
    def find_profile_file(self, entity_name: str) -> Optional[Path]:
        """
        Find the markdown file for an entity (case-insensitive, flexible matching).
        """
        if not self.kb_path.exists():
            return None
        
        # Try exact match first
        for prefix in ['character_', 'location_', 'term_']:
            filename = f"{prefix}{entity_name.replace(' ', '_')}.md"
            filepath = self.kb_path / filename
            if filepath.exists():
                return filepath
        
        # Try case-insensitive match
        entity_lower = entity_name.lower().replace(' ', '_')
        for file in self.kb_path.glob('*.md'):
            # Remove prefix and .md, compare
            name_part = file.stem
            for prefix in ['character_', 'location_', 'term_']:
                if name_part.startswith(prefix):
                    name_part = name_part[len(prefix):]
                    break
            
            if name_part.lower() == entity_lower:
                return file
        
        return None
    
    def update_profile(self, entity_name: str, instruction: str) -> Dict:
        """
        Update a profile based on instruction.
        
        Args:
            entity_name: Name of the entity
            instruction: What to change (e.g., "she has brown eyes, not blue")
            
        Returns:
            Dict with success status and message
        """
        profile_file = self.find_profile_file(entity_name)
        
        if not profile_file:
            return {
                'success': False,
                'message': f"Could not find profile for '{entity_name}'. Available entities: {self._list_entities()}"
            }
        
        # Read current profile
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception as e:
            return {
                'success': False,
                'message': f"Error reading profile: {e}"
            }
        
        # Ask AI to make the edit
        prompt = f"""You are editing a character/location/term profile markdown file.

CURRENT PROFILE:
{current_content}

USER INSTRUCTION: {instruction}

Your task: Update the profile according to the instruction. 

Rules:
1. Keep the markdown structure (# headers, ** bold **, etc.)
2. Keep the metadata section at top (Total Mentions, First Appearance)
3. Update ONLY the relevant sections
4. If adding new information, add it in the appropriate section
5. If correcting information, replace the incorrect part
6. Maintain the professional, factual tone

Return the COMPLETE updated profile (all sections, not just changes)."""

        result = self.ai.chat(prompt, project_context="")
        
        if not result['success']:
            return {
                'success': False,
                'message': f"AI edit failed: {result.get('error', 'Unknown error')}"
            }
        
        updated_content = result['response']
        
        # Save updated profile
        try:
            with open(profile_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            return {
                'success': True,
                'message': f"✅ Updated profile for '{entity_name}'",
                'file': str(profile_file)
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Error saving profile: {e}"
            }
    
    def add_to_profile(self, entity_name: str, instruction: str) -> Dict:
        """Add new information to a profile."""
        # Similar to update but with specific "add" instruction
        profile_file = self.find_profile_file(entity_name)
        
        if not profile_file:
            return {
                'success': False,
                'message': f"Could not find profile for '{entity_name}'"
            }
        
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception as e:
            return {
                'success': False,
                'message': f"Error reading profile: {e}"
            }
        
        prompt = f"""You are adding information to a character/location/term profile.

CURRENT PROFILE:
{current_content}

NEW INFORMATION TO ADD: {instruction}

Your task: Add this information to the appropriate section(s) of the profile.

Rules:
1. Keep all existing content
2. Add new information in the relevant section(s)
3. If no appropriate section exists, add it
4. Maintain markdown formatting
5. Keep factual and concise

Return the COMPLETE updated profile."""

        result = self.ai.chat(prompt, project_context="")
        
        if not result['success']:
            return {'success': False, 'message': "AI edit failed"}
        
        try:
            with open(profile_file, 'w', encoding='utf-8') as f:
                f.write(result['response'])
            
            return {
                'success': True,
                'message': f"✅ Added information to '{entity_name}' profile"
            }
        except Exception as e:
            return {'success': False, 'message': f"Error saving: {e}"}
    
    def remove_from_profile(self, entity_name: str, instruction: str) -> Dict:
        """Remove incorrect information from a profile."""
        profile_file = self.find_profile_file(entity_name)
        
        if not profile_file:
            return {
                'success': False,
                'message': f"Could not find profile for '{entity_name}'"
            }
        
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception as e:
            return {
                'success': False,
                'message': f"Error reading profile: {e}"
            }
        
        prompt = f"""You are removing incorrect information from a profile.

CURRENT PROFILE:
{current_content}

WHAT TO REMOVE: {instruction}

Your task: Remove the specified information while keeping everything else.

Rules:
1. Remove ONLY what's specified
2. Keep all other content intact
3. Maintain markdown formatting
4. If removing creates empty sections, remove the section header too

Return the COMPLETE updated profile."""

        result = self.ai.chat(prompt, project_context="")
        
        if not result['success']:
            return {'success': False, 'message': "AI edit failed"}
        
        try:
            with open(profile_file, 'w', encoding='utf-8') as f:
                f.write(result['response'])
            
            return {
                'success': True,
                'message': f"✅ Removed information from '{entity_name}' profile"
            }
        except Exception as e:
            return {'success': False, 'message': f"Error saving: {e}"}
    
    def merge_profiles(self, entity1: str, entity2: str) -> Dict:
        """
        Merge two entity profiles (when they're the same person/place/thing).
        """
        file1 = self.find_profile_file(entity1)
        file2 = self.find_profile_file(entity2)
        
        if not file1:
            return {'success': False, 'message': f"Could not find profile for '{entity1}'"}
        if not file2:
            return {'success': False, 'message': f"Could not find profile for '{entity2}'"}
        
        try:
            with open(file1, 'r', encoding='utf-8') as f:
                content1 = f.read()
            with open(file2, 'r', encoding='utf-8') as f:
                content2 = f.read()
        except Exception as e:
            return {'success': False, 'message': f"Error reading profiles: {e}"}
        
        prompt = f"""You are merging two profiles that describe the same entity.

PROFILE 1 ({entity1}):
{content1}

PROFILE 2 ({entity2}):
{content2}

Your task: Create ONE comprehensive profile that combines all information.

Rules:
1. Use the more complete name as the main title
2. Combine all sections intelligently (don't duplicate info)
3. Keep all unique details from both profiles
4. Resolve any contradictions (prefer more specific info)
5. Maintain markdown formatting

Return the COMPLETE merged profile."""

        result = self.ai.chat(prompt, project_context="")
        
        if not result['success']:
            return {'success': False, 'message': "AI merge failed"}
        
        # Save merged profile to file1, delete file2
        try:
            with open(file1, 'w', encoding='utf-8') as f:
                f.write(result['response'])
            
            file2.unlink()  # Delete the duplicate
            
            return {
                'success': True,
                'message': f"✅ Merged '{entity2}' into '{entity1}'. Deleted duplicate profile."
            }
        except Exception as e:
            return {'success': False, 'message': f"Error saving: {e}"}
    
    def _list_entities(self) -> str:
        """List all available entity names."""
        if not self.kb_path.exists():
            return "none"
        
        entities = []
        for file in self.kb_path.glob('*.md'):
            # Extract entity name from filename
            name = file.stem
            for prefix in ['character_', 'location_', 'term_']:
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    break
            entities.append(name.replace('_', ' '))
        
        return ', '.join(sorted(entities)[:10]) + ('...' if len(entities) > 10 else '')
    
    def execute_edit(self, command_dict: Dict) -> Dict:
        """
        Execute an edit command.
        
        Args:
            command_dict: Output from detect_edit_command()
            
        Returns:
            Dict with success status and message
        """
        cmd_type = command_dict['command_type']
        entity = command_dict['entity']
        
        if cmd_type == 'merge':
            merge_with = command_dict['merge_with']
            return self.merge_profiles(entity, merge_with)
        
        instruction = command_dict['instruction']
        
        if cmd_type in ['update', 'correct']:
            return self.update_profile(entity, instruction)
        elif cmd_type == 'add':
            return self.add_to_profile(entity, instruction)
        elif cmd_type == 'remove':
            return self.remove_from_profile(entity, instruction)
        else:
            return {
                'success': False,
                'message': f"Unknown command type: {cmd_type}"
            }
