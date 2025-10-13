import spacy
def test_spacy_installation():
    try:
        # Load the English model
        nlp = spacy.load("en_core_web_sm")
        print("Successfully loaded English model")
        # Test with sample text
        sample_text = "James Bond walked into the MI6 headquarters in London. He met with M and Q for a briefing."
        doc = nlp(sample_text)
        # Extract entities
        entities = [(ent.text, ent.label_) for ent in doc.ents]
        print(f"Extracted entities: {entities}")
        # Print success message
        print("SpaCy installation and model loading verified successfully!")
        return True
    except Exception as e:
        print(f"Error testing spaCy installation: {e}")
        return False
if __name__ == "__main__":
    test_spacy_installation()