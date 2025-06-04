import os


def create_project_structure():
    """
    Generates the 'mercadolivre_analytics' project directory
    and all specified files with concise headers.
    """

    project_root = "mercadolivre_analytics"

    # Ensure the root project directory exists before anything else
    os.makedirs(project_root, exist_ok=True)
    print(f"Created project root directory: {project_root}")

    structure = {
        "app.py": "# Main Dash application",
        "config": {
            "config.py": "# Configuration management",
            "api_config.py": "# ML API settings",
        },
        "src": {
            "models": {
                "products.py": "# Products and categories",
                "sellers.py": "# Seller information",
                "analytics.py": "# Business intelligence",
            },
            "extractors": {
                "ml_api_client.py": "# API client",
                "items_extractor.py": "# Product extraction",
                "competitors_extractor.py": "# Competitor data",
            },
            "transformers": {
                "data_cleaner.py": "# Data cleaning",
                "price_analyzer.py": "# Price analysis",
                "product_enricher.py": "# Product enrichment",
            },
            "loaders": {
                "database.py": "# DB connection",
                "data_loader.py": "# Data loading",
            },
            "services": {
                "market_service.py": "# Market analysis",
                "pricing_service.py": "# Pricing intelligence",
                "forecast_service.py": "# Demand forecasting",
            },
            "dashboard": {
                "layout.py": "# Dashboard layout",
                "components.py": "# Reusable components",
                "callbacks.py": "# Interactive callbacks",
            },
            "utils": {
                "db_utils.py": "# Database utilities",
                "api_utils.py": "# API helpers",
            },
        },
        "data": {
            "noneca_analytics.db": "# SQLite database",
        },
        "tests": {},  # Empty directory for test suite
        "requirements.txt": "# Project dependencies",
        "main.py": "# Main entry point",
    }

    print(f"Creating project structure for: {project_root}")
    # Now call _create_structure with the already existing project_root
    _create_structure(project_root, structure)
    print("Project structure created successfully!")


def _create_structure(current_path, structure):
    """
    Recursively creates directories and files based on the provided structure.
    """
    for name, content in structure.items():
        path = os.path.join(current_path, name)
        if isinstance(content, dict):
            # It's a directory
            os.makedirs(path, exist_ok=True)
            print(f"  Created directory: {path}")
            _create_structure(path, content)
        else:
            # It's a file
            with open(path, "w") as f:
                f.write(content + "\n")
            print(f"  Created file: {path}")


if __name__ == "__main__":
    create_project_structure()
