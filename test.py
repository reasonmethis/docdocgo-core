from langchain.prompts.prompt import PromptTemplate
import bs4
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import WebBaseLoader
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema import StrOutputParser
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores.chroma import Chroma
import os
os.environ["OPENAI_API_KEY"] = "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"

loader = WebBaseLoader(
    web_paths=("https://lilianweng.github.io/posts/2023-06-23-agent/",),
    bs_kwargs=dict(
        parse_only=bs4.SoupStrainer(
            class_=("post-content", "post-title", "post-header")
        )
    ),
)
docs = loader.load()

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
splits = text_splitter.split_documents(docs)

vectorstore = Chroma.from_documents(documents=splits, embedding=OpenAIEmbeddings(), persist_directory="./my-chroma-test")
retriever = vectorstore.as_retriever()

prompt = PromptTemplate.from_template("Answer this question: What is decomposition? \n\n using only the following information:\n{context}")
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


rag_chain = (
    {"context": retriever | format_docs}
    | prompt
    | llm
    | StrOutputParser()
)

print(rag_chain.invoke("What is decomposition?"))