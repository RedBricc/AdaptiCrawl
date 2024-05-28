# Longo Web Scraper
# Description
This tool was built to adaptively gather listed record information from a large number of sites.
It is designed to be easily configurable and adaptable to changes in the sites it scrapes.

It uses:
* Python 3.11.4
* [Selenium](https://www.selenium.dev/) to automate a web browser and scrape data from the DOM.
* [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) to parse the HTML.
* [css-inline](https://pypi.org/project/css-inline/) to inline the CSS.
* PostgreSQL 15.4 to store the data and [psycopg2](https://pypi.org/project/psycopg2/) to interact with the database.
* [office365](https://pypi.org/project/Office365-REST-Python-Client/) for image storage on Sharepoint.

Other dependencies are listed in the [requirements.txt](requirements.txt) file.

# Modules
Table of contents:
* [Classification](#classification)
* [DB](#db)
* [Element finder](#element-finder)
* [Preprocessing](#preprocessing)
* [Services](#services)
* [Scrapers](#scrapers)
* [Debug run](#debug-run)
* [Scheduler](#scheduler)

## Scheduler
Each day the scheduler will start a new [run](#runs),
which can include multiple [sessions](#scraping-sessions) for each [configured locale](#target-domains).
They are reordered to spread the locales from one domain as far apart as possible,
reducing the chance of being flagged as a bot.

### Run
For each session, the scheduler will start a new process and run the [catalog scraper](#catalog-scraper-module) for the [configured locale](#target-domains).
The number of processes that can run at the same time is limited by the [pool capacity](#scheduler-settings) setting.

### Scraping sessions
A session is a single execution of a [scraper](#scrapers) for a single configured url.

### Retry attempts
After the run is completed, the scheduler will retry each failed session up to the maximum number of retries set in the [retry attempts](#scheduler-settings) setting.
The retried sessions are ran one by one to avoid overloading the site and to evade detection as a bot.

## Debug run
If needed,
the scraper can be run in debug mode to inspect the generated tag tree for the data cleaning and tagging steps.
This is useful for troubleshooting issues with the scraper or to manually retry a failed session
without waiting for the next run.

DebugRun.py takes the following parameters:
* `domain`: The domain of the site.
* `locale`: The locale of the site.
* `url`: The URL of the site.
* `configuration`: OPTIONAL. The additional configuration for the site.
* `run_id`: OPTIONAL. The ID of the run. Default is 0.

Examples:
```shell
python DebugRun.py longo lv https://longo.lv/automasinu-katalogs
```

```shell
python DebugRun.py longo lt https://longo.lt/katalogas '{"interaction_buttons": ["#CookieBannerNotice > div.cookiebanner__main > div > div.cookiebanner__buttons > div > button.cb-btn.cb-btn-yellow.w50"], "preferred_pagination_handler": "VIEW_MORE"}' 100
```

## Scrapers
Table of contents:
* [Web scraper](#web-scraper-module)
* [Catalog scraper](#catalog-scraper-module)
* [Static scraper](#static-scraper-module)

### Web scraper module
The web scraper module contains all the necessary functions for establishing a connection with Selenium. It can be configured using [catalog scraper settings](#catalog-scraper-settings).
It uses [proxies](#proxy-service) to avoid detection. This module can be configured using [web scraper settings](#webscraper-settings).

If a connection cannot be established, the scraper will attempt to either use its own IP address if a proxy was used or use the first proxy from the list if no proxy was provided.

### Catalog scraper module
The goal of this module is to provide a simple interface for scraping catalog data from dynamic websites.
The scraper is designed with the following principles in mind:
* **Precision to a fault**: The scraper should be able to reliably identify at least 95% of the records on the site.
* **Resilience to changes**: The scraper should be able to handle changes in the site's formatting without breaking.
* **Adaptability**: The scraper should be easily configurable to scrape data from new sites.
* **Scalability**: The scraper should be able to handle hundreds of sites and thousands of records.
* **Stealth**: The scraper should be able to scrape data without being detected as a bot.
* **Stability**: The scraper should be able to run for long periods of time without crashing.

#### Usage

##### Adding a new site
To add a new site to the scraper, you need to add a new entry to [target_domains](#target-domains) in settings.
The key is the domain name of the site, and the value is a list of configured locales with the following required parameters:
* `locale`: The locale of the site.
* `url`: The URL of the site.
* `configuration`: OPTIONAL. The additional configuration for the site.

Optionally, you can add locale specific configurations using the `configuration` parameter.
It is strongly recommended to use the general configuration and only add this **if necessary**.
Adding unnecessary configurations can lead to unnecessary complexity and make the scraper less resilient to changes in the site.

The configuration can include the following parameters:

| Parameter                      | Description                                                                                                                                                                                                                                                                                                                      | Default value |
|--------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------|
| `interaction_buttons`          | A list of CSS selectors for buttons to allow the scraper to interact with the site. This is useful for sites that have popup modals or require a button to be clicked to load the data. Further details on how to get the CSS selectors can be found in the [Acquiring the CSS selectors](#acquiring-the-css-selectors) section. | []            |
| `ignored_cleaning_steps`       | A list of [cleaning steps](#html-cleaning) to ignore. This is useful for sites where a general cleaning step is not applicable.                                                                                                                                                                                                  | []            |
| `preferred_pagination_handler` | The preferred [pagination method](#pagination-handler). This is useful for sites that have multiple pagination methods or ads that include pagination.                                                                                                                                                                           | None          |
| `use_proxy`                    | Whether to use a [proxy](#proxies) for the site. This is useful for sites that block the scraper's IP address or have a low traffic limit.                                                                                                                                                                                       | False         |

Example:
```json
{
  "longo": [
    {
      "locale": "lv",
      "url": "https://longo.lv/automasinu-katalogs"
    },
    {
      "locale": "lt",
      "url": "https://longo.lt/katalogas",
      "configuration": {
        "interaction_buttons": [
          "#CookieBannerNotice > div.cookiebanner__main > div > div.cookiebanner__buttons > div > button.cb-btn.cb-btn-yellow.w50"
        ],
        "preferred_pagination_handler": "VIEW_MORE"
      }
    }
  ]
}
```

#### Troubleshooting

##### No records found
First, check the [logs](#logging-service) for any errors or warnings. If there are any, address them first.
Also check the [screenshots folder](#screenshots-folder) on Sharepoint for any screenshots of the site at the time of the error.

If the scraper is not finding any records, it is likely that:
* The site has changed formatting for one of the required [attributes](#attribute-rules).
* The site wasn't fully loaded when the scraper tried to scrape the data

To troubleshoot this, you can run the scraper in [debug mode](#debug-run) and inspect the generated tag tree for the data cleaning and tagging steps.
From there, you can adjust the attribute rules to match the new formatting or change the cleaning step settings in the [Catalog scraper settings](#catalog-scraper-settings) to ignore the new formatting.

If the site wasn't fully loaded, you can adjust the timing settings in the [Catalog scraper settings](#catalog-scraper-settings).

##### Pagination issues
If the scraper is not finding all the records, it is likely that:
* The site has changed the pagination method
* The site has a popup modal or requires a button to be clicked to load the data

To troubleshoot this, you can run the scraper in [debug mode](#debug-run) and inspect the generated logs and tag trees for the pagination method used as well as the results of the data cleaning and tagging steps.

If the site has changed the pagination method, you can inspect the site for the pagination method used and the results of the data cleaning and tagging steps.
For developers, you can adjust the [pagination method](#pagination-handler) in the [target domains](#target-domains) settings as well as the code in PaginationHandler.py to reliably identify the correct pagination method.
For other users, you can adjust the [pagination method](#pagination-handler) in the [target domains](#target-domains) settings to match the new pagination method.
However, this is discouraged as it can lead to unnecessary complexity and make the scraper less resilient to changes in the site.
Please contact the development team to further troubleshoot this issue and find a more resilient solution.

If the site has a popup modal or requires a button to be clicked to load the data, you can inspect the site for the popup modal or button and add the CSS selectors to the [target domains](#target-domains) settings.

### Static scraper module
Deprecated. This module is no longer in use, but the settings are still available for reference.
It might be removed or repurposed in the future.

## Services
Table of contents:
* [Catalog service](#catalog-service)
* [Image service](#image-service)
* [Logging service](#logging-service)
* [Proxy service](#proxy-service)
* [Settings service](#settings-service)
* [Stopword service](#stopword-service)
* [Table cache service](#table-cache-service)

### Catalog service
Manages [run](#runs), [session](#scraping-sessions), [record](#records), and [price](#prices) saving for the [catalog scraper](#catalog-scraper-module).
Record data is saved to the database while images are saved to [Sharepoint](#sharepoint).

Found records are saved based on the following rules:
* A new record record is created if the record is not found in the database by its alias.
* If the record record is found, the existing record is **not** updated unless it's missing its image.
* As described in [Image service](#image-service), if the image is not a [default image](#default-images), it's saved to [Sharepoint](#sharepoint) and the URL is saved to the database.
* The record [price](#prices) is always saved to the database.
* If the record is marked as not sold, but not found in the current session, its date sold is marked as yesterday.
* If the record is marked as sold, but found in the current session, its date sold is marked as null.

### Image service
Manages image storage on [Sharepoint](#sharepoint).

* **The record image** is saved in the "record_images" folder on Sharepoint, and the URL is saved to the database unless it's a [default image](#default-images). The image is saved with the record's alias as the file name.
* **Screenshots** for each run are saved in a separate folder on Sharepoint under "screenshots" for troubleshooting. The screenshots are saved with run_RUN_ID as the folder name and domain_locale_time as the file name. 
  * If the environment is PROD, then a screenshot will only be saved if the total record count is below the [record count warning](#catalog-scraper-settings) setting.
  * If the environment is STAGE, then a screenshot will always be saved.
  * If the environment is any other (e.g. DEV), then a screenshot will only be saved locally in the screenshots folder if the total record count is below the [record count warning](#catalog-scraper-settings) setting.

### Logging service
Manages logging for the scraper. 
It logs to the console and to a file located in the logs folder (longo-web-scraper/logs).
Each time the scraper is run, a new log file is created with scheduler_DATETIME as the file name.

The logging service uses the following log levels:

| Level       | Level name / number   | Description                                                                               |
|-------------|-----------------------|-------------------------------------------------------------------------------------------|
| DETAILED    | 18                    | Detailed debug information, typically of interest only when diagnosing specific problems. |
| LONGO_DEBUG | 19                    | General debug information.                                                                |
| INFO        | logging.INFO (20)     | Informational messages. Lowest logging level in STAGE environment.                        |
| WARNING     | logging.WARNING (30)  | Warning messages. Lowest logging level in PROD environment.                               |
| ERROR       | logging.ERROR (40)    | Error messages.                                                                           |
| CRITICAL    | logging.CRITICAL (50) | Critical error messages.                                                                  |
Note: The DETAILED and LONGO_DEBUG log levels are not part of the standard logging module and are used for more detailed debugging information.
The logging.DEBUG (10) level is not used to avoid spamming the logs with unnecessary information from imported libraries.

### Proxy service
Provides functionality for using [proxies](#proxies) to avoid detection.
When getting the whole list, it gets all the proxies from the database and returns them as a list.
A None value is added to the list to allow the scraper to use its own IP address if needed.

When getting a single proxy, it gets the first proxy from the list and returns it.

As described in (Web scraper module)[#web-scraper-module], the proxy is used to establish a connection with Selenium.

### Settings service
Provides functionality for getting [settings](#settings) for the scraper.
The settings are retrieved from the database and stored locally in a dictionary. 
When the scraper is not running, the settings are updated every 10 minutes.
If a setting is not found, an error is logged and an empty dictionary is returned.

### Stopword service
Deprecated. This module is no longer in use, see [classification](#classification).

### Table cache service
Provides functionality for caching the database tables.
This service is intended to be used for tables which aren't updated frequently.
The tables are cached in a dictionary and updated every 15 minutes while the scraper is not running.

When getting values, the first column is discarded as it is assumed to be the primary key.
If only one column remains, the values are returned as a list, otherwise the values are returned as a list of tuples.

## Preprocessing
Table of contents:
* [HTML cleaning](#html-cleaning)
* [Value tagging](#value-tagging)

### HTML cleaning
The HTML cleaning step removes unnecessary data from the site by stripping the HTML of unnecessary tags and attributes.
This allows the scraper to be more resilient to changes in the site's formatting.

HTML cleaning steps are defined below.

![HTML cleaning steps](images/HtmlCleaningSteps.jpg)

#### Create tag tree
The first step in the HTML cleaning process is to create a tag tree using BeautifulSoup for indexing and css inlining.

#### Add tag indexes
A `scraper-index` attribute is added to each tag to allow later modules to find a tag by its index.
The tags are indexed in the order they appear in the tag tree, staring with 0.

#### Inline CSS
The CSS rules are inlined from the `class` attribute to the `style` attribute using the site's stylesheets.
By default, the [css-inline](https://pypi.org/project/css-inline/) library is used, 
but if it fails the [Premailer](https://pypi.org/project/premailer/) library is used as a fallback.
Css inlining is necessary to allow the scraper to find the correct tags for the data cleaning and tagging steps.
The css-inline is much faster than Premailer,
but it's not as reliable and can fail to inline the CSS in some edge cases.

#### Make tag tree for cleaning
The inlined CSS is used to create a new tag tree for the cleaning steps.

#### Inline images
Images tags with the `background` or `background-image` attribute are added to the tag tree as `img` tags.

#### Remove comments
All comments are removed from the tag tree.

#### Remove invisible tags
Tags with styles
matching the [invisible_tag_regex](#catalog-scraper-settings) setting patterns are removed from the tag tree.

Example:
```json
{
  "invisible_tag_regex": [
    "display:\\s*none",
    "position:\\s*fixed",
    "text\\-decoration:\\s*line\\-through"
  ]
}
```

#### Remove excluded tags
Tags matching the tag types defined in the [excluded_tags](#catalog-scraper-settings) setting are removed.

Example:
```json
{
  "excluded_tags": [
    "script",
    "meta",
    "br"
  ]
}
```

#### Remove non-whitelisted attributes
Tags with attributes not defined in the [whitelisted_attributes](#catalog-scraper-settings) setting are removed.

Example:
```json
{
  "whitelisted_attributes": [
    "src",
    "href",
    "class"
  ]
}
```

#### Flatten text
Tags matching the tag types defined in the [flattened_tags](#catalog-scraper-settings) setting are removed,
and their text is added to the parent tag.

Example:
```json
{
  "flattened_tags": [
    "b",
    "i",
    "p"
  ]
}
```

#### Flatten special strings
Some special strings like 'EUR' might be included in separate tags (e.g., the `div` tag),
which are too broad and cannot be included in [flattened_tags](#catalog-scraper-settings).
These strings should be added to the [flattened_special_strings](#catalog-scraper-settings) setting.
When the scraper finds a tag with one of these strings, it will remove the tag and add the string to the parent tag.

Examples:
```json
{
  "flattened_special_strings": [
    "eur",
    "EUR",
    "€"
  ]
}
```

#### Remove redundant punctuation marks
Some punctuation marks don't add any value to the text and can be ignored.
These punctuation marks are defined in the [redundant_punctuation_marks](#catalog-scraper-settings) setting.
When the scraper finds a tag with one of these punctuation marks,
it will replace the punctuation mark with a single space.

Example:
```json
{
  "redundant_punctuation_marks": [
    "-",
    ":"
  ]
}
```

#### Remove punctuation whitespace
When a punctuation mark from the [punctuation_marks](#catalog-scraper-settings) setting is found,
the scraper will remove any whitespace before the punctuation mark.

Example:
```json
{
  "punctuation_marks": [
    ".",
    "?",
    "!"
  ]
}
```

#### Remove empty tags
Tags with no children and no text are removed from the tag tree.
The exceptions to this rule are tags defined in the [empty_tags](#catalog-scraper-settings) setting.

Example:
```json
{
  "empty_tags": [
    "img"
  ]
}
```

#### Remove stopwords
Deprecated. This step is disabled, see [classification](#classification).

#### Remove duplicate white space
All duplicate white space is removed from the text.

### Value Tagging
The value tagging step tags the text of the tag tree with attributes
defined in the [attribute rules](#attribute-rules) setting.
An attribute is a piece of data that the scraper is looking for on the site, 
for example, make, model or price of the car.

Attribute rules include the required following parameters:
* `name`: The attribute name. This value should be made up of letters from the **English alphabet and underscores.**
* `type`: The attribute type. For more information, see [AttributeParser](#attribute-parser).
* `tags`: A list of [attribute tags](#attribute-tags) to apply.

Optional parameters:
* `required`: If true then the attribute is required to be present on a potential record block.
* `default`: The default value for the attribute if it's not found. This is useful for attributes that are not marked as required.

#### Attribute tags
The scraper supports a number of attribute tags to find different types of data on the site.
They can be broadly split into these categories:
* [Data location](#data-location)
* [Data acquisition method](#data-acquisition-method)
* [Additional flags](#additional-flags)

##### Data location
* `text`: The scraper should look for this attribute in the text of a tag.
  * Usage example:
  ```json
    {
      "name": "price",
      "type": "float",
      "tags": [
        "text"
      ]
    }
  ```
* `attribute`: The scraper should look for this attribute in the attributes of a tag. If this tag is used, the `attribute_regex` parameter is required to be present. 
  * Usage example:
  ```json
    {
      "name": "link",
      "type": "link",
      "tags": [
        "attribute"
      ],
      "attribute_regex": "\\bhref$"
    }
  ```
* `image`: The scraper should look for this attribute in the image of a tag.
  * NOT IMPLEMENTED

##### Data acquisition method
* `regex_driven`: The scraper should use a regex to find this attribute. If this tag is used, the `regex` parameter is required to be present.
  * Usage example:
  ```json
    {
      "name": "year",
      "type": "text",
      "tags": [
        "text",
        "regex_driven"
      ],
      "regex": "\\b(19|20)\\d{2}(?!\\d)"
    }
  ```
* `example_driven`: The scraper should match the attribute value from the list of examples. If this tag is used, the `examples` parameter is required to be present.
  * Usage example:
  ```json
    {
      "name": "make",
      "type": "text",
      "tags": [
        "text",
        "example_driven"
      ],
      "examples": [
        "Audi",
        "BMW",
        "Opel"
      ]
    }
  ```

##### Additional flags
* `aggregate`: Indicates that the value of this attribute should include values from other attributes. Note that attribute rules are applied in sequence, so an attribute with the `aggregate` tag should be placed **after** the attributes it aggregates.
  * Usage example:
  ```json
    {
      "name": "title",
      "type": "text",
      "regex": "\\$MAKE\\$\\s?\\$MODEL\\$(\\s?\\$VARIANT\\$)?",
      "tags": [
        "text",
        "regex_driven",
        "aggregate"
      ]
    }
  ```
* `ignore_case`: Indicates that the regex should not be case-sensitive.
  * Usage example:
  ```json
    {
      "name": "make",
      "type": "text",
      "tags": [
        "text",
        "example_driven",
        "ignore_case"
      ],
      "examples": [
          "audi",
          "bmw",
          "opel"
      ]
    }
  ```
* `table_sourced`: Indicates that examples should be sourced from a database table. If this tag is used, the `source` parameter is required to be present.
  * Usage example:
  ```json
    {
      "name": "make",
      "type": "text",
      "tags": [
        "text",
        "example_driven",
        "table_sourced"
      ],
      "source": "makes"
    }
  ```
* `exclusive`: Indicates that the attribute should only be matched once in a given tag.
  * Usage example:
  ```json
    {
      "name": "make",
      "type": "text",
      "tags": [
        "text",
        "example_driven",
        "table_sourced",
        "exclusive"
      ],
      "source": "makes"
    }
  ```
* `fallback`: Indicates that this attribute rule should be used as a fallback if the previous attribute rules fail to find a value.
  * Usage example:
  ```json
  [
    {
      "name": "alias",
      "regex": "(?<=\\/?)[^\\/]+?(?=\\/?$)",
      "required": true,
      "type": "text",
      "default": "",
      "tags": [
        "attribute",
        "regex_driven"
      ],
      "attribute_regex": "\\bhref$"
    },
    {
      "name": "alias",
      "regex": "(?<=[\\/]?)[^\\/]{5,}?(?=([\\/\\.'][^\\/\\.]*)?$)",
      "required": false,
      "type": "text",
      "default": "",
      "tags": [
        "attribute",
        "regex_driven",
        "fallback"
      ],
      "attribute_regex": "\\b(id|onclick)$"
    }
  ]
  ```
* `anti_attribute`: Indicates that the potential record block should be ignored if this attribute is found.
  * Usage example:
  ```json
    {
      "name": "sold",
      "type": "text",
      "tags": [
        "text",
        "example_driven",
        "anti_attribute"
      ],
      "examples": [
        "sold",
        "pārdots"
      ]
    }
  ```
* `filtered`: Indicates that the attribute should be filtered using the regex from the `filter_regex` parameter. The resulting value will be from the start of the found value until the first match of the filter regex, stripped of surrounding whitespace.
  * Usage example:
  ```json
    {
      "name": "model",
      "type": "text",
      "tags": [
        "text",
        "regex_driven",
        "filtered"
      ],
      "regex": "(?<=\\$MAKE\\$,?)(\\s?[^\\s\\$]+){1,2}",
      "filter_regex": "\\,"
    }
  ```
  In this example, the found value "Astra, 1.6" would become just "Astra"
* `replace_similar`: Indicates that all similar values in the tree should be tagged as this attribute. It also applies all the other tags from the original attribute when searching.
  * Usage example:
  ```json
    {
      "name": "model",
      "type": "text",
      "tags": [
        "text",
        "regex_driven",
        "replace_similar"
      ],
      "regex": "(?<=\\$MAKE\\$,?)(\\s?[^\\s\\$]+){1,2}"
    }
    ```

## Element finder
Table of contents:
* [Attribute parser](#attribute-parser)
* [Block finder](#block-finder)
* [Pagination handler](#pagination-handler)

### Attribute parser
Parser for the attribute rules defined in the [attribute rules](#attribute-rules) setting.
Given a list of potential attribute values, the parser will attempt to find the correct value for each attribute.

The attribute parser supports the following types:
* `text`: Text data.
* `int`: Integer data.
* `float`: Float data.
* `link`: Link data.
* `image_link`: Image link data.

By default, the parser will take the first value found for the attribute, 
but if any `constraints` are defined in the [attribute parameters](#attribute-rules),
the parser will attempt to find the correct value based on the constraints.

The following constraints are supported:
* `discard_smaller_than`:
  * If the value is a number, the parser will discard any values smaller than the constraint. For example, the following rule would discard any values smaller than 50.7:
  ```json
    {
    "constraints": {
        "discard_smaller_than": "50.7"
      }
    }
  ```
  * If the value is a percentage, the parser will discard any values smaller than the percentage of the maximum value. For example, the following rule would discard any values smaller than 30% of the maximum value:
  ```json
    {
    "constraints": {
        "discard_smaller_than": "30%"
      }
    }
  ```
  
* `prioritize_nth_biggest`: The parser will prioritize the nth biggest value found. For example, the following rule would prioritize the third-biggest value found:
  ```json
    {
    "constraints": {
        "prioritize_nth_biggest": 3
      }
    }
  ```
NOTE:
The parser should be able to translate relative links to absolute links, 
except when parsing record images if the image was a background-image with a local path.
In this case, the parser will be unable to find the correct image URL and will return `None`.

For example, these three tags would be properly translated to absolute links:
```html
<img alt="Image with absolute link" class="record-image" src="https://img.longo.group/drz5zvoaf/image/upload/c_fill,h_813,w_1084/kne1910jbyp4m5ou7hfy.webp">
```
```html
<img alt="Image with relative link" class="record-image" src="/lv/record-images/sa34d54a.png">
```
```html
<div id="background image with absolute link" class="record-image" style="background-image: url('https://img.longo.group/drz5zvoaf/image/upload/c_fill,h_813,w_1084/kne1910jbyp4m5ou7hfy.webp')"></div>
```

But this tag would not:
```html
<div class="record-image" style="background-image: url('/lv/record-images/sa34d54a.png')"></div>
```

This is because the scraper has no reference to the site's file structure.
In most cases, this should not be an issue, 
as most sites use CDN networks to host their images and therefore have absolute links.

### Block finder
The block finder is used to find potential record blocks in the tagged tree.
A record block is defined as a tag 
which contains all the required [attributes](#attribute-rules) within itself or its children,
but does not contain any [anti-attributes](#additional-flags).

After finding all potential record blocks, 
the block finder will find the largest grouping of record blocks and return them as a list.
Two blocks are considered to be in the same grouping 
if they are within the [max_tag_distance](#catalog-scraper-settings) setting.

Block distance is measured in the number of tags between the two blocks.
For example, a tag has a distance of 0 from itself,
two sibling tags have a distance of 1 as they both share the same parent tag,  
and the following tags would have a distance of two, because of the wrapper tag between them:
```html
<body>
  <div class="wrapper">
      <div class="block" id="block1">
          <h1>Block 1</h1>
      </div>
  </div>
  <div class="block" id="block2">
      <h1>Block 2</h1>
  </div>
</body>
```

### Pagination handler
The pagination handler is used to find the next page of the site.
It supports the following pagination methods
* [INFINITE_SCROLL](#infinite-scroll): The site uses infinite scroll to load the next page.
* [PAGINATOR](#paginator): The site uses pagination to load the next page.
* [VIEW_MORE](#view-more): The site uses a button to load the next page.
* `NONE`: The site has no pagination and only has a single page.

#### Infinite scroll
By default, the pagination handler will attempt
to find the next page by first trying to scroll to the bottom of the page and checking if the page loads more tags
within the time frame allotted by the [scroll_delay](#catalog-scraper-settings) setting.
Crucially, the scraper will also scroll up by the amount 
defined in the [scroll_offset](#catalog-scraper-settings) setting to ensure that the catalog section is visible.
This is necessary
as some pages have large footers which may cover the entire screen and prevent the scraper from loading the next page.

If it does, the scraper will continue to scroll to the bottom of the page
until it reaches the [max_page_count](#catalog-scraper-settings) setting or no new tags are loaded.

#### Paginator
If the scraper is unable to find the next page using the infinite scroll method,
It will then attempt to look for a paginator, which is a list of links to the next pages.
It does so by finding the grouping of buttons which:
* Have the same parent tag
* Have the relevant page numbers as text
* Have a tag type defined in the [pagination_tags](#catalog-scraper-settings) setting
* Preferentially, has a parent with `paginator_classes` defined in the [catalog scraper settings](#catalog-scraper-settings) at a distance of `paginator_levels` from the button.
* Have the closest distance to the record blocks

Buttons which preceded the record blocks in the tag tree are discarded
as a page's paginator is presumed to be after the record blocks.

The scraper will then click the button up to [paginator_attempts](#catalog-scraper-settings) times.
More information about this can be found in the [Button click behavior](#button-click-behavior) section.

After clicking the paginator,
the scraper will wait [paginator_delay](#catalog-scraper-settings) seconds for the page to load.

#### View more
If a paginator is not found, the scraper will then attempt to look for a view more button.
The scraper identifies potential view more buttons 
by looking for buttons with text matching the [view_more_aliases](#catalog-scraper-settings) setting.
Similar to the paginator method, the scraper will discard buttons which preceded the record blocks in the tag tree.

After finding potential view more buttons, 
the scraper will select the closest one to the record blocks and click it up to [view_more_attempts](#catalog-scraper-settings) times.
More information about this can be found in the [Button click behavior](#button-click-behavior) section.

After clicking the view more button,
the scraper will wait [view_more_load_delay](#catalog-scraper-settings) seconds for the page to load.

#### Button click behavior
When attempting to click a button, 
the scraper can encounter a number of problems starting with the button not being found.
This can happen if the button element was present on the page when the scraper saved the page's tag tree,
but was removed by the time the scraper attempted to click it.
This can be solved by increasing timing related settings in the [catalog scraper settings](#catalog-scraper-settings).

If the button is found, the scraper can encounter a number of problems when attempting to click it.
While by default, the scraper attempts to scroll to the button and then pressing the enter key after selecting it,
this can fail if the button is not intractable or if the page is not fully loaded.
This can be solved by increasing timing related settings in the [catalog scraper settings](#catalog-scraper-settings)
or by adding the close button for a blocking popup the [interaction_buttons](#catalog-scraper-settings) setting.

If the enter key method fails, the scraper will attempt to click the button using the Selenium click method.
This can fail if the button is not intractable or if the element is covered by a popup.
This can be solved 
by adding the close button for a blocking popup the [interaction_buttons](#catalog-scraper-settings) setting.

#### Handler failover
Either by finding a pagination method by following the order described above or by using
the `preferred_pagination_handler` defined in the [target domains](#target-domains) settings, 
the scraper will wait for the second page to load and then attempt to find new record blocks.

If the scraper is unable to find new record blocks, it is assumed that the pagination method failed.
In this case, the scraper will attempt 
to find the next page using the order described above, skipping the failed methods.

## DB
Table of contents:
* [Credentials](#credentials)
* [Database connector](#database-connector)

### Credentials
To ensure the security of the database, the credentials are stored in the Credentials.py file.
This file **is not** included in the repository and should be added manually to the project.

This file contains the following credentials:
* `SERVER`: The host IP of the database.
* `DATABASE`: The name of the database.
* `USERNAME`: The username for the database.
* `PASSWORD`: The password for the database.
* `ENVIRONMENT`: The environment of the scraper. This is used to determine the logging level and whether to save screenshots to Sharepoint. The possible values are:
  * `DEV`: Development environment.
  * `STAGE`: Staging environment.
  * `PROD`: Production environment.
* `SHAREPOINT_ID`: The user ID for Sharepoint.
* `SHAREPOINT_SECRET`: The secret for Sharepoint.
* `SHAREPOINT_URL`: The base URL for Sharepoint.

### Database connector
It is used by other [services](#services) to establish a connection to the database.

## Classification
Deprecated. This module is no longer in use, but the settings are still available for reference.
It's intended to be used for classifying arbitrary text into a list of categories.
It is not fully implemented and is not used in the scraper, but it might be repurposed in the future.

# Settings
All settings are grouped in the following categories:
* [Webscraper settings](#webscraper-settings)
* [Scheduler settings](#scheduler-settings)
* [Catalog scraper settings](#catalog-scraper-settings)
* [Static scraper settings](#static-scraper-settings)
* [Attribute rules](#attribute-rules)
* [Target domains](#target-domains)

## Webscraper settings
The webscraper settings are used to configure the [web scraper module](#web-scraper-module). 
All web scraper settings are required and do not have default values.

| Setting          | Description                                                                                                                              |
|------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| loading_delay    | The amount of time in seconds to wait for the page to load.                                                                              |
| headless         | Whether to run the scraper in headless mode.                                                                                             |
| tag_count_cutoff | The minimum number of tags required to consider the page loaded. If the page has fewer tags, the scraper will wait for the page to load. |
| retry_count      | The amount of times the scraper will wait for the page to load before giving up.                                                         |
| retry_interval   | The amount of time in seconds the scraper will wait for the page to load before retrying.                                                |

## Scheduler settings
The scheduler settings are used to configure the [scheduler module](#scheduler).

| Setting                    | Description                                                                                                                                                                                    |
|----------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| scrape_on_startup          | Boolean value determining whether the scraper should run on startup.                                                                                                                           |
| retry_attempts             | Amount of times the scraper will attempt to [retry](#retry-attempts) a given run before giving up.                                                                                             |
| retry_startup_time_minutes | Amount of time in minutes to wait before starting a [retry run](#retry-attempts). This is important to separate the retry session from the previous run.                                       |
| retry_wait_time_minutes    | Amount of time in minutes to wait after a [retry session](#retry-attempts) before starting a new one.                                                                                          |
| pool_capacity              | Amount of processes the scraper will be running at a time. It is suggested to keep this value to at most twice the core count of the machine as each selenium session is quite resource heavy. |
| process_timeout_minutes    | Amount of time in minutes before a [scraping session](#scraping-sessions) is considered to be stuck and is killed.                                                                             |

## Catalog scraper settings
| Setting                     | Description                                                                                                                                                                                                                                                                                              |
|-----------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| min_record_count           | The minimum amount of records required to consider the page loaded. If the page has fewer records, the scraper will attempt to wait `retry_timeout` seconds before retrying. <br/> If the total record count scraped is lower than this value, the scrape is marked as failed and an error is logged. |
| record_count_warning       | If the total amount of scraped records is below this value, a [screenshot](#screenshots-folder) of the page is taken and saved to Sharepoint. If the environment is STAGE, then a screenshot will always be saved.                                                                                      |
| scroll_delay                | Used for infinite scroll pages. Determines the maximum amount of time in seconds to wait for the next page to load.                                                                                                                                                                                      |
| scroll_offset               | Used for infinite scroll pages. Determines the amount of pixels the scraper will scroll up after scrolling to the bottom of the page. <br/> This is useful for pages that have footers larger than the full screen as many pages will not load the next page if the catalog section isn't visible.       |
| max_page_count              | Maximum amount of pages to load before quitting. <br/> This setting is important to avoid infinite loops in pages. It should not exceed 200 as this is the maximum page available in Autoplius. <br/> All [target domains](#target-domains) should be configured to fit within this limit.               |
| retry_timeout               | Amount of time in seconds to wait before attempting to read the page data again. This is used when the found record count is bellow `min_record_count`.                                                                                                                                                |
| max_tag_distance            | The maximum distance in tags between [record blocks](#block-finder) to consider them as part of the same group.                                                                                                                                                                                         |
| max_pagination_distance     | The maximum distance in tags between the [pagination handler](#pagination-handler) and the [record blocks](#block-finder) to consider the pagination handler as part of the same group.                                                                                                                 |
| view_more_attempts          | The amount of times the scraper will attempt to click the view more button before giving up.                                                                                                                                                                                                             |
| view_more_load_delay        | The amount of time in seconds to wait for the page to load after clicking the view more button.                                                                                                                                                                                                          |
| paginator_levels            | The maximum amount of levels to search for the paginator class.                                                                                                                                                                                                                                          |
| paginator_delay             | The amount of time in seconds to wait for the page to load after clicking the paginator button.                                                                                                                                                                                                          |
| paginator_attempts          | The amount of times the scraper will attempt to click the paginator button before giving up.                                                                                                                                                                                                             |
| upload_record_images       | Boolean value determining whether the scraper should upload record images to Sharepoint.                                                                                                                                                                                                                |
| hash_record_images         | Boolean value determining whether the scraper should hash record images before uploading them to Sharepoint.                                                                                                                                                                                            |
| pagination_tags             | The tags to look for when searching for the next page.                                                                                                                                                                                                                                                   |
| excluded_tags               | The tags to exclude from the tag tree. See [Remove excluded tags](#remove-excluded-tags).                                                                                                                                                                                                                |
| whitelisted_attributes      | The attributes to include in the tag tree. See [Remove non-whitelisted attributes](#remove-non-whitelisted-attributes).                                                                                                                                                                                  |
| flattened_tags              | The tags to flatten. See [Flatten text](#flatten-text).                                                                                                                                                                                                                                                  |
| flattened_special_strings   | The special strings to flatten. See [Flatten special strings](#flatten-special-strings).                                                                                                                                                                                                                 |
| invisible_tag_regex         | The regex patterns to remove invisible tags. See [Remove invisible tags](#remove-invisible-tags).                                                                                                                                                                                                        |
| empty_tags                  | The tags to remove if they are empty. See [Remove empty tags](#remove-empty-tags).                                                                                                                                                                                                                       |
| punctuation_marks           | The punctuation marks to remove whitespace from. See [Remove punctuation whitespace](#remove-punctuation-whitespace).                                                                                                                                                                                    |
| redundant_punctuation_marks | The punctuation marks to remove. See [Remove redundant punctuation marks](#remove-redundant-punctuation-marks).                                                                                                                                                                                          |
| view_more_aliases           | The text to look for when searching for the view more button.                                                                                                                                                                                                                                            |
| paginator_classes           | The classes to look for when searching for the paginator.                                                                                                                                                                                                                                                |

## Static scraper settings
Deprecated. See [Static scraper](#static-scraper-module).

## Attribute rules
A list of attribute rules to be used by the [attribute parser](#attribute-parser).

## Target domains
A list of target domains to be used by the [catalog scraper](#catalog-scraper-module).

# Data storage

## Database schema

### Default images

### Makes

### Models

### Prices

### Proxies

### Runs

### Scraping sessions

### Settings table

### Records

## Sharepoint

### Record image storage
Record images are stored in the "record_images" folder on Sharepoint.
The images are saved with the name pattern `DOMAIN_ALIAS.EXTENSION`.

### Screenshots folder
Screenshots for each run are saved in a separate folder on Sharepoint under "screenshots" for troubleshooting.
The screenshots are saved with `run_RUN_ID` as the folder name and `DOMAIN_LOCALE_TIME` as the file name.

# Development Setup

## Prerequisites
* Python 3.11.4 or later
* PostgreSQL 15.4 or later

## Installation

## Running the tests
