"""Knowledge Extraction Orchestrator - Main workflow controller."""
from pathlib import Path
from typing import Dict

from .entity_extractor import EntityExtractor
from .profile_builder import ProfileBuilder
from .query_analyzer import QueryAnalyzer
from ..llm_integration import GeorgeAI


class KnowledgeExtractor:
    """Main orchestrator for knowledge extraction and retrieval."""

    def __init__(self, george_ai: GeorgeAI, project_path: str):
        """Create a knowledge extractor bound to a George AI instance."""
        if george_ai is None:
            raise ValueError("A GeorgeAI instance is required for knowledge extraction.")

        self.ai = george_ai
        self.project_path = Path(project_path)
        self.project_path.mkdir(parents=True, exist_ok=True)

        self.kb_path = self.project_path / "knowledge_base"
        self.kb_path.mkdir(parents=True, exist_ok=True)

        knowledge_client = self.ai.get_knowledge_client()
        self.extractor = EntityExtractor()
        self.profile_builder = ProfileBuilder(knowledge_client, str(self.kb_path))
        self.query_analyzer = QueryAnalyzer(self.ai, str(self.kb_path))

        self.entities: Dict[str, object] = {}
        self.processing_complete = False

    def process_manuscript(self, text: str, filename: str) -> Dict:
        """Run the full extraction pipeline against the supplied manuscript."""
        print(f"\n{'=' * 60}")
        print(f"[START] Starting knowledge extraction for: {filename}")
        print(f"{'=' * 60}\n")

        # Phase 1: Extract entities
        print("Phase 1: Extracting entities...")
        initial_entities = self.extractor.extract_initial_entities(text)
        print(f"  Found {len(initial_entities)} potential entities")

        # Phase 2: Classify entities
        print("\nPhase 2: Classifying entities...")
        self.entities = self.extractor.classify_entities(text)
        summary = self.extractor.get_summary()
        print(f"  Characters: {summary['character']}")
        print(f"  Locations: {summary['location']}")
        print(f"  Terms: {summary['term']}")

        # Phase 3: Build detailed profiles
        print("\nPhase 3: Building detailed profiles (this may take a while)...")

        characters = self.extractor.get_entities_by_type('character')
        for entity in characters:
            try:
                self.profile_builder.build_character_profile(entity.name, text, entity)
            except Exception as exc:  # noqa: BLE001 - downstream models can raise varied errors
                print(f"  [WARN] Error building profile for {entity.name}: {exc}")

        locations = self.extractor.get_entities_by_type('location')
        for entity in locations:
            try:
                self.profile_builder.build_location_profile(entity.name, text, entity)
            except Exception as exc:  # noqa: BLE001 - downstream models can raise varied errors
                print(f"  [WARN] Error building profile for {entity.name}: {exc}")

        terms = self.extractor.get_entities_by_type('term')
        for entity in terms[:5]:  # Limit term profiles to avoid runaway calls
            try:
                self.profile_builder.build_term_profile(entity.name, text, entity)
            except Exception as exc:  # noqa: BLE001 - downstream models can raise varied errors
                print(f"  [WARN] Error building profile for {entity.name}: {exc}")

        self.processing_complete = True

        print(f"\n{'=' * 60}")
        print("[OK] Knowledge extraction complete!")
        print(f"{'=' * 60}\n")

        return {
            'total_entities': len(self.entities),
            'characters': summary['character'],
            'locations': summary['location'],
            'terms': summary['term'],
            'kb_path': str(self.kb_path),
        }

    def answer_query(self, user_question: str) -> Dict:
        """Generate an answer using the built knowledge base."""
        if not self.processing_complete:
            return {
                'success': False,
                'error': 'Knowledge base not ready. Please upload and process a manuscript first.',
            }

        context = self.query_analyzer.build_context_for_query(user_question)
        result = self.ai.chat(user_question, context)
        success_flag = result.get('success') if isinstance(result, dict) else 'n/a'
        print(f"[ANSWER][RAW] result_type={type(result)} success={success_flag}")

        answer_text = ''
        model_name = None
        fallback_used = False

        if isinstance(result, dict):
            answer_text = result.get('response') or ''
            model_name = result.get('model')
            if result.get('success') and answer_text:
                print("[ANSWER][OK] Returning AI-composed answer")
                return {
                    'success': True,
                    'response': answer_text,
                    'model': model_name,
                    'context_used': len(context),
                }

            fallback_reason = result.get('error') or answer_text or 'No AI answer available.'
        else:
            fallback_reason = str(result)

        # Fallback: return the gathered context with a notice so the UI is never blank.
        fallback_used = True
        reason_text = fallback_reason if fallback_reason else 'Unknown issue.'
        fallback_message = (
            "⚠️ I couldn't get an AI-generated answer just now. "
            f"Reason: {reason_text}\n\n"
            "Here's the relevant context I found:\n\n"
        )
        context_excerpt = context.strip() if context else 'No context available.'
        if len(context_excerpt) > 1500:
            context_excerpt = context_excerpt[:1500].rstrip() + '…'
        fallback_response = f"{fallback_message}{context_excerpt}"

        print("[ANSWER][FALLBACK] Using knowledge-base fallback response")
        return {
            'success': True,
            'response': fallback_response,
            'model': model_name or 'knowledge-base-fallback',
            'context_used': len(context),
            'fallback_used': fallback_used,
            'fallback_reason': fallback_reason,
        }

    def get_knowledge_base_summary(self) -> Dict:
        """Return a snapshot of knowledge base status and counts."""
        return {
            'processing_complete': self.processing_complete,
            'entities': self.extractor.get_summary(),
            'total_profiles': len(list(self.kb_path.glob('*.md'))),
            'kb_path': str(self.kb_path),
        }
