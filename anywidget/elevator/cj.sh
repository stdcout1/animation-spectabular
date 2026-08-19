uv run jupyter nbconvert --to pdf \
  --execute \
  --ExecutePreprocessor.store_widget_state=True \
  --template acm \
  --TemplateExporter.extra_template_basedirs="../../report/latex_templates" \
  --output Elevator \
  "Elevator.ipynb"