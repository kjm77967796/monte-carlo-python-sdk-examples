# Databricks notebook source
# MAGIC %md # Environment Setup

# COMMAND ----------

#Install the Monte Carlo Python Library (Notebook scoped)
#More info here: https://docs.databricks.com/libraries/notebooks-python-libraries.html#install-a-library-with-pip
%pip install pycarlo

# COMMAND ----------

# DBTITLE 1,Find/Set API Credentials
# Monte Carlo Credentials stored in DBX Secret Key Repo called "monte-carlo-creds":
mcd_id = dbutils.secrets.get(scope = "monte-carlo-creds", key = "mc-id")
mcd_token = dbutils.secrets.get(scope = "monte-carlo-creds", key = "mc-token")

# Other variables which you can customize:
mcd_profile = ""

# COMMAND ----------

# DBTITLE 1,Build a List of Available Reports
from pycarlo.core import Client, Query, Session

client = Client(session=Session(mcd_id=mcd_id, mcd_token=mcd_token, mcd_profile=mcd_profile))
query = Query()
query.get_insights().__fields__('name', 'reports')

response = client(query).get_insights

insight_name_to_report_mapping = {}
for insight in response:
    name = insight.name

    for report in insight.reports:
        # Some Insights have a .html report as well, we want to filter for just the .csv reports
        if report.name.endswith('.csv'):
            insight_name_to_report_mapping[name] = report.name

# COMMAND ----------

# DBTITLE 1,Create User Input Widgets
dbutils.widgets.multiselect(
    'INSIGHTS TO DOWNLOAD',
    defaultValue="incident_history",
    choices=list(insight_name_to_report_mapping.keys())
)
dbutils.widgets.text("SCHEMA TO WRITE TO", "mcd_insights")

# COMMAND ----------

# DBTITLE 1,Runtime Variables (Pulled From Input Widgets)
insight_names = dbutils.widgets.get("INSIGHTS TO DOWNLOAD").split(',')
insight_report_names = [insight_name_to_report_mapping[insight] for insight in insight_names]
table_schema = dbutils.widgets.get("SCHEMA TO WRITE TO")

# COMMAND ----------

# MAGIC %md # Load Insights to DBX

# COMMAND ----------

from pycarlo.core import Client, Query, Mutation, Session
import requests
from pyspark.sql.functions import *
import io
import pandas as pd
from datetime import *

client = Client(session=Session(mcd_id=mcd_id, mcd_token=mcd_token,mcd_profile=mcd_profile))
today = datetime.today()

for i in range(len(insight_report_names)):
    print("Looking for Insight Report: {}".format(insight_report_names[i]))
    query=Query()
    query.get_report_url(insight_name=insight_names[i],report_name=insight_report_names[i]).__fields__('url')
    report_url=client(query).get_report_url.url
    r = requests.get(report_url).content
    
    # Customize the naming scheme of the loaded tables here:
    table_name = "mcd_insight_" + insight_names[i]
    filename = insight_report_names[i]
    
    #Read data into pandas to convert to csv
    df=pd.read_csv(io.StringIO(r.decode('utf-8')))  
    #display(df) #Uncomment to see the data before it is loaded to a table
    
    #changing column spaces to underscores (if there are any)
    df.columns = df.columns.str.replace(' ','_')
    print('Creating Spark Data Frame')
    DF = spark.createDataFrame(df).withColumn("load_date", lit(date(today.year, today.month, today.day)))

    #Load Data to Databricks DELTA lake
    DF.write.mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{table_schema}.{table_name}")
    print("Created table: {}.{}".format(table_schema,table_name))
    print("\n") 

# COMMAND ----------

df = spark.sql("SHOW TABLES IN {} like 'mcd_insight_*'".format(table_schema))
display(df)
