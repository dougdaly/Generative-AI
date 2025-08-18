<H1>Overview</H1>
This repo contains a several demos of various GenAI techniques. Many of these are drawn from other existing demos, and then modified to run with the latest python libraries and provide added insight into the techniques demonstrated. In those cases, reference sources are included in the Jupyter notebook.</br></br>
<H2>Topics</H2>
These noteboooks focus primarily on Image generation with some multi-modal techniques and foundational concepts. They are:
<ul><li>
    <b>Variational Autoencoders (VAE):</b> Foundational for generative AI! The notebook VAE_Example.ipynb compares a traditional auto-encoder with a VAE to provide understanding of what the VAE offers.
</li><li>
    <b>Diffusion:</b>A common form of image generation where a VAE is leveraged to learn a class of images.
        annotated_diffusion.ipynb provides the theory, concepts and formulae for the progressive noise addition done during training. At the end, it generates an image trained from the MNIST fashion dataset.
        score_based_diffusion.ipynb uses a score-based approach to diffusion using an ODE solver.
        Stable_Diffusion.ipynb leverages existing HuggingFace diffusion models with a CLIP text encoder, resulting in image generation based on a text prompt.
</li><li>
    <b>Stability.ai</b> provides an API interface to generate or modify an existing image. Stability_API_Demo.ipynb shows how to mask images, overlay images, change backgrounds and other tasks with a few lines of code.
</li><li>
    <b>GAN (Generalized Adversarial Network)</b> generates images through having 2 neural networks compete with each other -- a generator (to make the fake image) and a discriminator which tells whether an input image is real or not. The demo builds a GAN based on a celebrity dataset and discusses potential pitfalls of this technique.
</li><li>
    <b>CLIP (Contrastive Language-Image Pretraining)</b> shows multi-modal AI where texts and images are projected onto a common space so a text prompt may yield a relevant image and an image results in a text description. Both of these tasks happen in this demo.
        CLIP-from-ground-up.ipynb shows how to build a CLIP model based on the flickr dataset which pairs several thousand images with text descriptions. For curiousity sake, the demo ends with 5 new example images, and uses the model to return a relevant caption.
        CLIP_tuning.ipynb covers the more practical case. Begin with a working general CLIP model, then tune it with images more relevant to a use case. This demo tunes with a number of ground images all viewed from the sky, then shows how the relationship improved after training.
</li><li>
    <b>RAG (retrieval augmented generation):</b> with multi-modal GenAI understood, RAG allows users to query a known dataset.
        Building_a_multimodal_RAG.ipynb queries both stored text and images based on the user's prompt.
</li>
</ul>