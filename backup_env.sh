#
# To activate this environment, use
#
#     $ conda activate ai_backup
#
# To deactivate an active environment, use
#
#     $ conda deactivate
pip freeze > requirements.txt
conda env export --from-history > environment.yml
conda create --name ai_backup --clone ai
