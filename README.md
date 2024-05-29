# AdaptiCrawl
Adaptive web scraper for long-term scraping purposes

##NOTE: THIS IS NOT A STRIPPED-DOWN VERSION OF THE REAL IMPLEMENTATION. IT SHOULD ONLY BE USED FOR REFERENCE PURPOSES.

# Setup
1. Open the AdaptiCrawl directory in your terminal of choice
2. Execute ```pip install -r requirements.txt```
3. Create a Postgres 14.9 database
4. Open scraper/main/python/db
5. Create the file Credentials.py using the provided template
```python
SERVER = '127.0.0.1'
DATABASE = 'scraper_db'
USERNAME = 'your_username'
PASSWORD = 'your_password'

ENVIRONMENT = 'dev'
```
6. Edit the settings.json file located in scraper/main/resources to match your needs
7. Edit scraper/main/python/db/Database.py to match your needs

# Running the scheduler
1. Open the AdaptiCrawl directory in your terminal of choice
2. Execute ```python scraper/main/python/Scheduler.py``` to start the scheduler 

# Running an individual scrape
1. Open the AdaptiCrawl directory in your terminal of choice
2. Execute ```python scraper/main/python/scrapers/CatalogScraper.py``` to start the worker
