import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

# Add parent to path if needed
current_dir = Path(__file__).parent
george_dir = current_dir.parent
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

# Import necessary modules
from llm_integration import create_george_ai, GeorgeAI
from parsers.parsers import read_manuscript_file
from knowledge_extraction.query_analyzer import QueryAnalyzer # We'll reuse this for its KB file loading

logger = logging.getLogger(__name__)

class KnowledgeExtractor:
    """
    Orchestrates the new Three-Pass Automatic Knowledgebase Generator (AKG)
    and handles query analysis for the chat.
    """
    
    def __init__(self, ai_router_instance: GeorgeAI, project_path: str):
        """
        Initialize the orchestrator.
        
        Args:
            ai_router_instance (GeorgeAI): A pre-initialized (fast) AI instance for routing.
            project_path (str): The full path to the project's root directory.
        """
        self.project_path = Path(project_path)
        self.knowledge_base_path = self.project_path / "knowledge_base"
        self.knowledge_base_path.mkdir(parents=True, exist_ok=True)
        
        # This analyzer is used for the CHAT, not KB generation
        self.query_analyzer = QueryAnalyzer(ai_router_instance, project_path=str(project_path))

        # --- Initialize the Three-Pass AI models ---
        try:
            self.ai_scout = create_george_ai(model="gemini-2.0-flash", use_cloud=True)
            self.ai_researcher = create_george_ai(model="gemini-2.5-flash", use_cloud=True)
            self.ai_analyst = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True)
            logger.info("Three-Pass AKG AI models initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize all AI models: {e}", exc_info=True)
            raise
            
        # --- Load KB Sheet Templates ---
        self.kb_templates = self._load_kb_templates()

    def _load_kb_templates(self) -> Dict[str, str]:
        """Loads the story bible templates from the backend/prompts directory."""
        templates = {}
        # Prompts have been moved to backend/prompts/
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        prompt_dir = project_root / "backend" / "prompts"
        template_files = {
            "Character": "kb_sheet_character.txt",
            "Location": "kb_sheet_location.txt",
            "Event": "kb_sheet_event.txt",
            "Unique Element": "kb_sheet_unique_element.txt"
        }
        for key, filename in template_files.items():
            try:
                path = prompt_dir / filename
                with open(path, 'r', encoding='utf-8') as f:
                    templates[key] = f.read()
                logger.info(f"Successfully loaded template: {filename}")
            except Exception as e:
                logger.error(f"FATAL: Failed to load template {filename}: {e}")
                templates[key] = f"ERROR: Could not load template for {key}"
        return templates

    def _read_manuscript(self, manuscript_filename: str) -> str:
        """Reads the full manuscript text from the project directory."""
        manuscript_path = self.project_path / manuscript_filename
        if not manuscript_path.exists():
            logger.error(f"Manuscript file not found: {manuscript_path}")
            raise FileNotFoundError(f"Manuscript file {manuscript_filename} not found.")
        
        logger.info(f"Reading manuscript: {manuscript_filename}")
        return read_manuscript_file(str(manuscript_path))

    def generate_knowledge_base(self, manuscript_filename: str) -> Dict[str, Any]:
        """
        Executes the new Three-Pass AKG workflow.
        """
        logger.info(f"--- STARTING: Three-Pass AKG for project {self.project_path.name} ---")
        try:
            full_text = self._read_manuscript(manuscript_filename)
        except Exception as e:
            return {'success': False, 'error': str(e)}

        # --- PASS 1: ENTITY IDENTIFICATION (The "Scout") ---
        logger.info("AKG Pass 1: Identifying all entities...")
        entities = self._pass_1_scout(full_text)
        if not entities:
            logger.error("AKG Pass 1 failed: No entities were identified.")
            return {'success': False, 'error': 'Pass 1 failed: No entities identified.'}
        
        logger.info(f"AKG Pass 1 complete: Found {len(entities)} entities.")
        
        # --- SEQUENTIAL PROCESSING (Pass 2 & 3) ---
        files_created = 0
        for i, entity in enumerate(entities):
            entity_name = entity.get('name')
            entity_type = entity.get('type')
            
            if not entity_name or not entity_type:
                logger.warning(f"Skipping invalid entity: {entity}")
                continue

            logger.info(f"--- Processing Entity {i+1}/{len(entities)}: '{entity_name}' ({entity_type}) ---")
            
            try:
                # --- PASS 2: RAW DATA COLLECTION (The "Researcher") ---
                logger.info(f"AKG Pass 2: Collecting raw data for '{entity_name}'...")
                raw_data_dossier = self._pass_2_researcher(full_text, entity_name)
                if not raw_data_dossier:
                    logger.warning(f"AKG Pass 2 failed: No raw data found for '{entity_name}'.")
                    continue
                
                # --- PASS 3: PROFILE SYNTHESIS (The "Analyst") ---
                logger.info(f"AKG Pass 3: Synthesizing profile for '{entity_name}'...")
                profile_content = self._pass_3_analyst(raw_data_dossier, entity_name, entity_type)
                if not profile_content:
                    logger.error(f"AKG Pass 3 failed: Could not synthesize profile for '{entity_name}'.")
                    continue
                    
                # --- SAVE THE FILE ---
                self._save_kb_file(entity_name, entity_type, profile_content)
                files_created += 1

            except Exception as e:
                logger.error(f"Failed to process entity '{entity_name}': {e}", exc_info=True)
                # Continue to the next entity
        
        logger.info(f"--- FINISHED: Three-Pass AKG ---")
        logger.info(f"Successfully created {files_created} of {len(entities)} possible knowledge base files.")
        
        return {
            'success': True,
            'entities_found': len(entities),
            'files_created': files_created
        }

    def _pass_1_scout(self, full_text: str) -> List[Dict[str, str]]:
        """Pass 1: Use Gemini 2.0 Flash to scan the text and identify entities."""
        prompt = f"""
        You are a literary analyst. Read the following manuscript and identify a comprehensive list of all named entities.
        Group them into four categories:
        1.  "Character" (all named characters, even minor ones)
        2.  "Location" (planets, cities, buildings, starships, regions)
        3.  "Event" (named historical events, battles, incidents, treaties)
        4.  "Unique Element" (named technology, magic systems, organizations, species, key items)
        
        Respond ONLY with a single JSON object. The object should have keys "characters", "locations", "events", and "unique_elements".
        Each key should have a value that is a list of strings.
        Example:
        {{
          "characters": ["Captain Eva", "Hugh", "Linda"],
          "locations": ["The Citadel", "V'tar", "The Medusa"],
          "events": ["The Siege of V'tar", "The First Light Incident"],
          "unique_elements": ["Stasis Field", "The K'ryll", "Voidsong Amulet"]
        }}

        --- MANUSCRIPT TEXT START ---
        {full_text}
        --- MANUSCRIPT TEXT END ---
        """
        
        try:
            result = self.ai_scout.chat(prompt, temperature=0.1, timeout=180) # Give it 3 minutes
            if not result['success']:
                raise Exception(f"Pass 1 AI call failed: {result.get('error')}")
            
            # Parse the JSON response
            response_text = result['response'].strip().replace("```json", "").replace("```", "")
            data = json.loads(response_text)
            
            # Re-format into the list of dicts we need
            entities = []
            for name in data.get("characters", []):
                entities.append({"name": name, "type": "Character"})
            for name in data.get("locations", []):
                entities.append({"name": name, "type": "Location"})
            for name in data.get("events", []):
                entities.append({"name": name, "type": "Event"})
            for name in data.get("unique_elements", []):
                entities.append({"name": name, "type": "Unique Element"})
                
            return entities
        except Exception as e:
            logger.error(f"AKG Pass 1 (Scout) failed: {e}", exc_info=True)
            return []

    def _pass_2_researcher(self, full_text: str, entity_name: str) -> str:
        """Pass 2: Use Gemini 2.5 Flash to gather all raw data for a single entity."""
        prompt = f"""
        You are a meticulous researcher. Scan the entire manuscript provided below.
        Your only task is to find and extract *every* passage, sentence, or fact that mentions or describes the entity: "{entity_name}".
        
        Compile all this information into a single, comprehensive, unformatted dossier.
        Include direct quotes and any inferred facts. Be thorough.

        --- MANUSCRIPT TEXT START ---
        {full_text}
        --- MANUSCRIPT TEXT END ---

        Raw Data Dossier for "{entity_name}":
        """
        
        try:
            result = self.ai_researcher.chat(prompt, temperature=0.0, timeout=180) # Give it 3 minutes
            if not result['success']:
                raise Exception(f"Pass 2 AI call failed: {result.get('error')}")
            
            return result['response'].strip()
        except Exception as e:
            logger.error(f"AKG Pass 2 (Researcher) failed for '{entity_name}': {e}", exc_info=True)
            return ""

    def _pass_3_analyst(self, raw_data_dossier: str, entity_name: str, entity_type: str) -> str:
        """Pass 3: Use Gemini 2.5 Pro to synthesize the raw data into a structured sheet."""
        
        # 1. Get the correct template
        template = self.kb_templates.get(entity_type)
        if not template or template.startswith("ERROR:"):
            logger.error(f"Cannot synthesize profile: No valid template found for type '{entity_type}'.")
            return ""
            
        prompt = f"""
        You are a highly skilled analytical author's assistant. Your job is to fill out a structured knowledge base sheet.
        
        You will be given a template for the sheet and a "raw data dossier" containing all known facts about the entity.
        Your task is to meticulously populate *every* field in the template using *only* the information from the data dossier.
        Do not make up any information.
        If information for a field is not present in the dossier, leave that field blank.
        
        The entity is: "{entity_name}"
        
        --- TEMPLATE ---
        {template}
        --- END TEMPLATE ---
        
        --- RAW DATA DOSSIER ---
        {raw_data_dossier}
        --- END RAW DATA DOSSIER ---
        
        Filled Sheet for "{entity_name}":
        """
        
        try:
            result = self.ai_analyst.chat(prompt, temperature=0.2, timeout=180) # Give it 3 minutes
            if not result['success']:
                raise Exception(f"Pass 3 AI call failed: {result.get('error')}")
            
            return result['response'].strip()
        except Exception as e:
            logger.error(f"AKG Pass 3 (Analyst) failed for '{entity_name}': {e}", exc_info=True)
            return ""

    def _save_kb_file(self, entity_name: str, entity_type: str, content: str):
        """Saves the generated profile content to a .md file."""
        
        # Sanitize entity name for filename
        safe_filename = "".join(c for c in entity_name.replace(" ", "_") if c.isalnum() or c == '_').lower()
        
        # Determine prefix from type
        prefix = entity_type.lower().replace(" ", "_")
        
        filename = f"{prefix}_{safe_filename}.md"
        filepath = self.knowledge_base_path / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Successfully saved knowledge base file: {filename}")
        except Exception as e:
            logger.error(f"Failed to save knowledge base file {filename}: {e}", exc_info=True)

    # --- Query Analyzer Methods ---
    # These methods are for the CHAT, not the AKG generation
    
    def analyze_and_get_context(self, user_question: str) -> (Dict[str, Any], str):
        """
        Analyzes a user's query and loads the appropriate context.
        (This is the entry point for the chat API)
        """
        # 1. Analyze Query
        analysis = self.query_analyzer.analyze_query(user_question)
        
        if analysis is None:
            logger.error(f"Query analysis failed for: {user_question}")
            return None, "My analysis of your request failed. Please try rephrasing."
            
        # 2. Load Context Files
        context_string = self.query_analyzer.load_context_files(analysis)
        
        return analysis, context_string