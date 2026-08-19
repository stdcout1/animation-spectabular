uv run jupyter nbconvert --to pdf \
  --execute \
  --ExecutePreprocessor.store_widget_state=True \
  --TagRemovePreprocessor.enabled=True \
  --TagRemovePreprocessor.remove_cell_tags='{"remove_cell"}' \
  --TagRemovePreprocessor.remove_input_tags='{"remove_input", "hidden"}' \
  --TagRemovePreprocessor.remove_all_outputs_tags='{"remove_output", "hidden"}' \
  --no-prompt \
  --template acm \
  --TemplateExporter.extra_template_basedirs="../../report/latex_templates" \
  --output Elevator \
  "Elevator.ipynb"