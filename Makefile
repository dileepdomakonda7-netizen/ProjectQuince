.PHONY: demo pipeline test test-all validate grade judges fast compare install clean

# Quick demo (3 products, ~15 seconds)
demo:
	python3 demo.py

# Full pipeline (all 10 products, all channels)
pipeline:
	python3 pipeline.py

# Fast pipeline (skip LLM grading and judges)
fast:
	python3 pipeline.py --fast

# Run unit tests (no API key needed)
test:
	python3 test_validator.py

# Run all tests including integration (no API key needed)
test-all:
	python3 test_validator.py && python3 test_integration.py

# Validate existing hooks (no API key needed)
validate:
	python3 validator.py

# Brand voice grading
grade:
	python3 brand_voice_grader.py

# Quality judges + composite score
judges:
	python3 quality_judges.py

# Quality judges without LLM (no API key needed)
judges-fast:
	python3 quality_judges.py --skip-llm

# Compare all configured providers in parallel
compare:
	python3 compare_providers.py

# Install dependencies
install:
	pip install -r requirements.txt

# Remove generated output files
clean:
	rm -f generated_hooks.json validation_report.json grading_report.json
	rm -f quality_report.json composite_report.json
	rm -rf provider_outputs/
