from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Models are imported elsewhere (e.g., app/models/__init__.py) to avoid circular imports.
# Do not import models directly here if they import Base from this module.