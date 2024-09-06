"""
agentic_arxiv_paper_finder_loader.py

This function sets up an agent to dynamically search for one or more papers 
on a given topic and returns the URL links to the paper.

Agent Design Notes

Agent has the following features:

1.  State is defined by `AgentState` class which is a sub-class of `TypedDict`.  Key is `messages` and value is an `Annotated` list.  This will be a list of `AIMessages`, `HumanMessages` and `ToolMessages`.

2.  Agent has access to tools in the list `tool_belt`.

3.  LLM model defined to be an OpenAI model using Langchain's ChatOpenAI wrapper.

4.  This agent leverages OpenAI function calling feature - hence the need to use `bind_tools` to bind the list of tools to our instance of the model.

5.  Graph nodes and associated functions: 
-   an `agent` node; associated function is `call_model` method
-   an `action` node: associated function is `tool_node` method
-   `END` node: represents the terminal node.
-   The entry point will be the `agent` node.  

6.  Graph edges:
-   conditional edges from `agent` node to either `action` node or `END` node: routing is determined by the `should_continue` method.
-   unconditional edge from `action` node to `agent` node

"""

# Imports
import re

from langchain_community.tools.arxiv.tool import ArxivQueryRun
from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from langchain_openai import ChatOpenAI
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
import operator
from langchain_core.messages import BaseMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, END
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage


system_prompt = """\
You are a smart research assistant. Use the search engine to look up information. \
You are allowed to make multiple calls (either together or in sequence). \
Only look up information when you are sure of what you want. \
"""

sample_user_input = {
    "messages" : [HumanMessage(content="What is the url of the paper on BERT on Arxiv?  Please return the URL of the paper on Arxiv in JSON format.")]
}


class ArxivAgentState(TypedDict):
  messages: Annotated[list, add_messages]


class ArxivPaperAgent:
    def __init__(self, 
                 model,
                 tools,
                 system_prompt):
        self.system_prompt = system_prompt
        graph = StateGraph(ArxivAgentState)
        graph.add_node("agent", self.call_model)
        graph.add_node("action", self.call_tool)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", self.should_continue, 
                                    {'action': 'action', END: END})
        graph.add_edge("action", "agent")
        self.graph = graph.compile()
        self.tools = {t.name: t for t in tools}
        self.model = model.bind_tools(tools)
        return
    
    def call_model(self, state: ArxivAgentState):
        messages = state["messages"]
        if self.system_prompt:
            messages = [SystemMessage(content=self.system_prompt)] + messages
        response = self.model.invoke(messages)
        return {"messages" : [response]}

    def call_tool(self, state: ArxivAgentState):
        tool_calls = state['messages'][-1].tool_calls
        results = []
        for t in tool_calls:
            print(f"Calling: {t}")
            result = self.tools[t['name']].invoke(t['args'])
            results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=str(result)))
        print("Back to the model!")
        return {'messages': results}
    
    def should_continue(self, state: ArxivAgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "action"
        return END


def get_arxiv_paper_url(model=ChatOpenAI(model="gpt-4o", temperature=0),
                        tools = [ArxivQueryRun()],
                        system_prompt=system_prompt,
                        user_message=""):
    # Instantiate the arxiv paper url bot
    arxiv_bot = ArxivPaperAgent(model=model,
                                tools=tools,
                                system_prompt=system_prompt)

    # Invoke the agent and save response
    response = arxiv_bot.graph.invoke(user_message)

    try:
        # Last message content is the required output
        # NOTE !!! it is not yet a well-formatted URL
        jsonstring = response["messages"][-1].content

        # Using regex to extract - 
        # NOTE!!! Hope to use Langchain output parser in a future version
        url_pattern = r'\"https://[\w.\/]+\"'
        match = re.search(url_pattern, jsonstring)

        if match:
            url = match.group()
        else:
            url = None
    except Exception as e:
        print(f'exception encountered: {e} ')
        url = None
    return response, url
