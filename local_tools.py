from langchain_experimental.utilities import PythonREPL
from langchain_core.tools import tool
import requests
from io import BytesIO
from typing import Annotated
from openai import OpenAI
from support import get_device
from langchain_tavily import TavilySearch # For web search
from langchain_core.messages import convert_to_messages

# For putting images into a grid
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.axes_grid1 import ImageGrid
import PIL.Image
import os
import glob

# Tools and helper functions to help AI agents perform their tasks.

# Initialization
#   Identify the GPU device
device = get_device()
#   Initialize OpenAI client
client = OpenAI()


# Tools
#       For web search agent
web_search = TavilySearch(max_results=3)

#       For image generator agent using dall-e-3.
repl = PythonREPL()
@tool
def python_repl_tool(
    code: Annotated[str, "The python code to execute to generate your image."],
):
    """Use this to execute python code. If you want to see the output of a value,
    you should print it out with `print(...)`. This is visible to the user."""
    try:
        result = repl.run(code)
    except BaseException as e:
        return f"Failed to execute. Error: {repr(e)}"
    result_str = f"Successfully executed:\n\`\`\`python\n{code}\n\`\`\`\nStdout: {result}"
    return (
        result_str + "\n\nIf you have completed all tasks, respond with FINAL ANSWER."
    )

#       For image generator agent using dall-e-3
def genImage(input)->str:
    '''Generate an image based on a text prompt'''
    response = client.images.generate(
        model="dall-e-3",
        prompt = input,
        size = "1024x1024",
        quality = "hd",
        n=1,
    )
    url = response.data[0].url
    return url
#       For image generator agent using dall-e-3
def saveImage(url:str, filename:str)->str:
    '''Save an image from a URL to a local file'''
    response = requests.get(url)
    img = PIL.Image.open(BytesIO(response.content))
    if not filename.endswith(".png"):
        filename = f"{filename}.png"
    else:
        filename = '.'.join(filename.split('.')[:2])
    img.save(filename)
    img.show()
    return filename


#       For image generation agent using stable diffusion or the dall-e-3.
def saveThumbnail(filename:str, thumbnail_filename:str)->str:
    '''Create and save a 100x100 pixel thumbnail of an image'''
    img = PIL.Image.open(filename)
    img.thumbnail((100, 100))
    if not thumbnail_filename.endswith(".png"):
        thumbnail_filename = f"{thumbnail_filename}.png"
    else:
        thumbnail_filename = '.'.join(thumbnail_filename.split('.')[:2])
    img.save(thumbnail_filename)
    return thumbnail_filename


# Helper functions
#       Generic system prompt for ai agents
def make_system_prompt(suffix: str) -> str:
    return (
        "You are a helpful AI assistant, collaborating with other assistants."
        " Use the provided tools to progress towards answering the question."
        " If you are unable to fully answer, that's OK, another assistant with different tools "
        " will help where you left off. Execute what you can to make progress."
        " If you or any of the other assistants have the final answer or deliverable,"
        " prefix your response with FINAL ANSWER so the team knows to stop."
    )


#       Makes the status output look nice
def pretty_print_messages(update, last_message=False):
    is_subgraph = False
    if isinstance(update, tuple):
        ns, update = update
        # skip parent graph updates in the printouts
        if len(ns) == 0:
            return

        graph_id = ns[-1].split(":")[0]
        print(f"Update from subgraph {graph_id}:")
        print("\n")
        is_subgraph = True

    for node_name, node_update in update.items():
        update_label = f"Update from node {node_name}:"
        if is_subgraph:
            update_label = "\t" + update_label

        print(update_label)
        print("\n")

        messages = convert_to_messages(node_update["messages"])
        if last_message:
            messages = messages[-1:]

        for m in messages:
            pretty_print_message(m, indent=is_subgraph)
        print("\n")
        
def pretty_print_message(message, indent=False):
    pretty_message = message.pretty_repr(html=True)
    if not indent:
        print(pretty_message)
        return

    indented = "\n".join("\t" + c for c in pretty_message.split("\n"))
    print(indented)



def display_image_grid():
    def find_images_glob(folder_path):
        image_files = []
        # You can specify multiple patterns for different image types
        image_files.extend(glob.glob(os.path.join(folder_path, '*thumbnail.png')))
        image_files.sort()
        images = [PIL.Image.open(image_file) for image_file in image_files]
        return images

    images = find_images_glob('.')

    # Create a figure
    # figsize starts with width
    fig = plt.figure(figsize=(12., 8.))
    grid = ImageGrid(fig, 111, nrows_ncols=(5, 6), axes_pad=0.2)

    # Iterate over the grid and display images
    for ax, im in zip(grid[:len(images)], images):
        ax.imshow(im) # Ensure image data type is appropriate
        ax.axis('off') # Turn off axis labels and ticks
        word = ' '.join(os.path.splitext(os.path.basename(im.filename))[0].split('_')[:-1])
        ax.set_title(f"{word[0]} - {word}", fontsize=9)  # Set title to filename without extension
    for ax in grid[26:]:
        ax.axis('off')
    plt.show()