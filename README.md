# AdaptiCrawl
Adaptive web scraper for long term scraping purposes

# Setup
1. Open the AdaptiCrawl directory in your terminal of choice
2. Execute ```pip install -r requirements.txt```
3. Create a postgres 14.9 database
4. Open scraper/src/main/python/db
5. Create the file Credentials.py using the provided template
```python
SERVER = '127.0.0.1'
DATABASE = 'scraper_db'
USERNAME = 'your_username'
PASSWORD = 'your_password'

ENVIRONMENT = 'dev'
```
6. Edit the settings.json file located in scraper/src/main/resources to match your needs
7. Edit scraper/src/main/python/db/Database.py to match your needs

# Running the scheduler
1. Open the AdaptiCrawl directory in your terminal of choice
2. Execute ```python scraper/src/main/python/Scheduler.py``` to start the scheduler 

# Running an individual scrape
1. Open the AdaptiCrawl directory in your terminal of choice
2. Execute ```python scraper/src/main/python/scrapers/CatalogScraper.py``` to start the worker
