import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import os

st.set_page_config(page_title="L&T AI Financial Analyst", layout="wide")
st.title("🤖 L&T Financial Analyst (Charts + Memory)")

# 1. API Key & DB Setup
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    st.error("Please add OPENAI_API_KEY to Secrets.")
    st.stop()

@st.cache_resource
def init_db():
    db_file = "lnt_data.db"
    con = duckdb.connect(db_file)
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx", engine="openpyxl")
        con.execute("CREATE OR REPLACE TABLE pnl_data AS SELECT * FROM df_pnl")
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx", engine="openpyxl")
        con.execute("CREATE OR REPLACE TABLE ut_data AS SELECT * FROM df_ut")
    con.close()
    return SQLDatabase.from_uri(f"duckdb:///{db_file}", view_support=False)

db = init_db()

# 2. Memory Setup (Persistent Chat)
msgs = StreamlitChatMessageHistory(key="chat_messages")
memory = ConversationBufferMemory(memory_key="chat_history", chat_memory=msgs, return_messages=True)

# 3. Enhanced Prompt for Accuracy
full_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a senior L&T Financial Analyst. Use 'pnl_data' and 'ut_data'. 
    RULES FOR ACCURACY:
    - ALWAYS check table schemas before querying.
    - If asked for a trend or comparison, suggest a chart.
    - Use 'Amount in USD' for financial totals.
    - If the user asks for a chart, provide the data in a clear table first."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# 4. Agent Setup
llm = ChatOpenAI(model="gpt-4o", temperature=0) # Temp 0 for maximum accuracy
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type="openai-tools",
    prompt=full_prompt
)

# 5. Chat & Chart Logic
for msg in msgs.messages:
    st.chat_message(msg.type).write(msg.content)

if prompt := st.chat_input("Ask: Plot the revenue trend for FMCG"):
    st.chat_message("human").write(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Analyzing and calculating..."):
            # Load memory into the execution context
            hist = memory.load_memory_variables({})["chat_history"]
            response = agent_executor.invoke({"input": prompt, "chat_history": hist})
            
            # 6. Chart Logic: If the agent provides data, we can visualize it
            st.write(response["output"])
            
            # Example: Simple keyword trigger for a Plotly chart
            if "revenue" in prompt.lower() and "trend" in prompt.lower():
                try:
                    # Quick fetch for a chart (Direct query to avoid hallucination)
                    con = duckdb.connect("lnt_data.db")
                    chart_df = con.execute("SELECT Month, SUM(\"Amount in USD\") as Revenue FROM pnl_data GROUP BY Month ORDER BY Month").df()
                    fig = px.line(chart_df, x="Month", y="Revenue", title="Revenue Trend Analysis")
                    st.plotly_chart(fig)
                    con.close()
                except:
                    pass
