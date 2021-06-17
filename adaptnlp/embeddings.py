# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/04_embeddings.ipynb (unless otherwise specified).

__all__ = ['logger', 'EmbeddingResult', 'EasyWordEmbeddings', 'EasyStackedEmbeddings', 'EasyDocumentEmbeddings']

# Cell
import logging, torch
from typing import List, Dict, Union
from collections import defaultdict, OrderedDict

from fastcore.basics import mk_class
from fastcore.xtras import dict2obj
from fastcore.dispatch import typedispatch
from flair.data import Sentence
from flair.embeddings import (
    Embeddings,
    WordEmbeddings,
    StackedEmbeddings,
    FlairEmbeddings,
    DocumentPoolEmbeddings,
    DocumentRNNEmbeddings,
    TransformerWordEmbeddings,
)

from .model_hub import FlairModelHub, HFModelHub, FlairModelResult, HFModelResult

# Cell
_flair_hub = FlairModelHub()
_hf_hub = HFModelHub()

# Cell
logger = logging.getLogger(__name__)

# Internal Cell
@typedispatch
def _make_sentences(text:str, as_list=False) -> Union[List[Sentence], Sentence]:
    return [Sentence(text)] if as_list else Sentence(text)

# Internal Cell
@typedispatch
def _make_sentences(text:list, as_list=False) -> Union[List[Sentence], Sentence]:
    if all(isinstance(t,str) for t in text):
        return [Sentence(t) for t in text]
    elif all(isinstance(t, Sentence) for t in text):
        return text

# Internal Cell
@typedispatch
def _make_sentences(text:Sentence, as_list=False) -> Union[List[Sentence], Sentence]:
    return [text] if as_list else text

# Internal Cell
@typedispatch
def _get_embedding_model(model_name_or_path:HFModelResult) -> TransformerWordEmbeddings:
    return TransformerWordEmbeddings(model_name_or_path.name)

# Internal Cell
@typedispatch
def _get_embedding_model(model_name_or_path:FlairModelResult) -> Union[FlairEmbeddings, WordEmbeddings]:
    nm = model_name_or_path.name
    try:
        return WordEmbeddings(nm.strip('flairNLP/'))
    except:
        return FlairEmbeddings(nm.strip('flairNLP/'))

# Internal Cell
@typedispatch
def _get_embedding_model(model_name_or_path:str) -> Union[TransformerWordEmbeddings, WordEmbeddings, FlairEmbeddings]:
    res = _flair_hub.search_model_by_name(model_name_or_path, user_uploaded=True)
    if len(res) < 1:
        # No models found
        res = _hf_hub.search_model_by_name(model_name_or_path, user_uploaded=True)
        if len(res) < 1:
            raise ValueError(f'Embeddings not found for the model key: {model_name_or_path}, check documentation or custom model path to verify specified model')
        else:
            return TransformerWordEmbeddings(res[0].name) # Returning the first should always be the non-fast option
    else:
        nm = res[0].name
        try:
            return WordEmbeddings(nm.strip('flairNLP/'))
        except:
            return FlairEmbeddings(nm.strip('flairNLP/'))

# Cell
from fastcore.basics import mk_class
mk_class('DetailLevel', **{o:o.lower() for o in 'High,Medium,Low'.split(',')},
         doc="All possible naming conventions for DetailLevel with typo-proofing")

# Cell
class EmbeddingResult:
    """
    A result class designed for Embedding models
    """
    def __init__(self, sentence:Sentence):
        self._sentence = sentence

    @property
    def sentence_embeddings(self) -> torch.tensor:
        """
        All embeddings in `sentence` (if available)
        """
        return self._sentence.get_embedding()

    @property
    def token_embeddings(self) -> torch.tensor:
        """
        All embeddings from the individual tokens in `sentence` with original order in shape (n, embed_dim)
        """
        return torch.stack([tok.get_embedding() for tok in self._sentence], dim=0)

    @property
    def tokenized_inputs(self) -> str:
        """
        The original tokenized inputs
        """
        return self._sentence.to_tokenized_string()

    @property
    def inputs(self) -> str:
        """
        The original input
        """
        return self._sentence.to_original_text()

    def to_dict(self, detail_level:DetailLevel=DetailLevel.Low):
        o = OrderedDict()
        o.update({'inputs':self.inputs,
                  'sentence_embeddings':self.sentence_embeddings,
                 'token_embeddings':self.token_embeddings})
        if detail_level == 'medium' or detail_level == 'high':
            # Return embeddings/word pairs and indicies, and the tokenized input
            o.update({
                tok.text:{
                    'embeddings':tok.get_embedding(),
                    'word_idx':tok.idx
                } for tok in self._sentence
            })
            o.update({
                'tokenized_inputs':self.tokenized_inputs
            })
        if detail_level == 'high':
            # Return embeddings/word pairs, indicies, and the original Sentence object
            o.update({tok.text:{
                'embeddings':tok.get_embedding(),
                'word_idx':tok.idx
                } for tok in self._sentence})
            o.update({'sentence':self._sentence})
        return o

    def __repr__(self):
        s = f"{self.__class__.__name__}:" + " {"
        s += f'\n\tInputs: {self.inputs}'
        if self.token_embeddings is not None: s += f'\n\tToken Embeddings Shape: {self.token_embeddings.shape}'
        if self.sentence_embeddings is not None: s += f'\n\tSentence Embeddings Shape: {self.sentence_embeddings.shape}'
        return s + '\n}'

# Internal Cell
def _format_results(embeds:list, detail_level:DetailLevel=None):
    """
    Generates either a list of `EmbeddingResult`s or a single based upon `detail_level` and their length
    """
    res = [EmbeddingResult(embed) for embed in embeds]
    return [o.to_dict(detail_level) for o in res] if detail_level is not None else res

# Cell
class EasyWordEmbeddings:
    """Word embeddings from the latest language models

    Usage:

    ```python
    >>> embeddings = adaptnlp.EasyWordEmbeddings()
    >>> embeddings.embed_text("text you want embeddings for", model_name_or_path="bert-base-cased")
    ```
    """

    def __init__(self):
        self.models: Dict[Embeddings] = defaultdict(bool)

    def embed_text(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        model_name_or_path: Union[str, HFModelResult, FlairModelResult] = "bert-base-cased",
        detail_level:DetailLevel = DetailLevel.Low,
        raw:bool = False
    ) -> List[EmbeddingResult]:
        """Produces embeddings for text

        **Parameters**:
        * `text` - Text input, it can be a string or any of Flair's `Sentence` input formats
        * `model_name_or_path` - The hosted model name key, model path, or an instance of either `HFModelResult` or `FlairModelResult`
        * `detail_level` - A level of detail to return. By default is None, which returns a EmbeddingResult, otherwise will return a dict
        * `raw` - A boolean of whether to skip generating an EmbeddingResult or dictionary. Mostly for dev, default is False

        **Return**:
        * A list of either EmbeddingResult's or dictionaries with information
        """
        # Convert into sentences
        sentences = _make_sentences(text)

        # Load correct Embeddings module
        self.models[model_name_or_path] = _get_embedding_model(model_name_or_path)
        embedding = self.models[model_name_or_path]
        embeds = embedding.embed(sentences)

        return _format_results(embeds, detail_level) if not raw else embeds

    def embed_all(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        model_names_or_paths:List[str] = [],
        detail_level:DetailLevel=DetailLevel.Low,
        raw:bool = False,
    ) -> List[EmbeddingResult]:
        """Embeds text with all embedding models loaded

        **Parameters**:
        * `text` - Text input, it can be a string or any of Flair's `Sentence` input formats
        * `model_names_or_paths` -  A list of model names
        * `detail_level` - A level of detail to return. By default is None, which returns a EmbeddingResult, otherwise will return a dict
        * `raw` - A boolean of whether to skip generating an EmbeddingResult or dictionary. Mostly for dev, default is False

        **Return**:
        * A list of either EmbeddingResult's or dictionaries with information
        """
        # Convert into sentences
        sentences = _make_sentences(text)

        if model_names_or_paths:
            for embedding_name in model_names_or_paths:
                sentences = self.embed_text(
                    sentences, model_name_or_path=embedding_name, raw=True
                )
        else:
            for embedding_name in self.models.keys():
                sentences = self.embed_text(
                    sentences, model_name_or_path=embedding_name, raw=True
                )
        return _format_results(sentences, detail_level) if not raw else embeds

# Cell
class EasyStackedEmbeddings:
    """Word Embeddings that have been concatenated and "stacked" as specified by flair

    Usage:

    ```python
    >>> embeddings = adaptnlp.EasyStackedEmbeddings("bert-base-cased", "gpt2", "xlnet-base-cased")
    ```

    **Parameters:**

    * `embeddings` - Non-keyword variable number of strings specifying the embeddings you want to stack
    """

    def __init__(self, *embeddings: str):
        print("May need a couple moments to instantiate...")
        self.embedding_stack = []

        # Load correct Embeddings module
        for model_name_or_path in embeddings:
            self.embedding_stack.append(_get_embedding_model(model_name_or_path))

        assert len(self.embedding_stack) != 0
        self.stacked_embeddings = StackedEmbeddings(embeddings=self.embedding_stack)

    def embed_text(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        detail_level:DetailLevel = DetailLevel.Low,
        raw:bool = False
    ) -> List[EmbeddingResult]:
        """Stacked embeddings

        **Parameters**:
        * `text` - Text input, it can be a string or any of Flair's `Sentence` input formats
        * `detail_level` - A level of detail to return. By default is None, which returns a EmbeddingResult, otherwise will return a dict
        * `raw` - A boolean of whether to skip generating an EmbeddingResult or dictionary. Mostly for dev, default is False

        **Return**:
        * A list of either EmbeddingResult's or dictionaries with information
        """
        # Convert into sentences
        sentences = _make_sentences(text, as_list=True)

        # Unlike flair embeddings modules, stacked embeddings do not return a list of sentences
        self.stacked_embeddings.embed(sentences)

        return _format_results(sentences, detail_level) if not raw else embeds

# Cell
class EasyDocumentEmbeddings:
    """Document Embeddings generated by pool and rnn methods applied to the word embeddings of text

    Usage:

    ```python
    >>> embeddings = adaptnlp.EasyDocumentEmbeddings("bert-base-cased", "xlnet-base-cased", methods["rnn"])
    ```

    **Parameters:**

    * `embeddings` - Non-keyword variable number of strings referring to model names or paths
    * `methods` - A list of strings to specify which document embeddings to use i.e. ["rnn", "pool"] (avoids unncessary loading of models if only using one)
    * `configs` - A dictionary of configurations for flair's rnn and pool document embeddings
    ```python
    >>> example_configs = {"pool_configs": {"fine_tune_mode": "linear", "pooling": "mean", },
    ...                   "rnn_configs": {"hidden_size": 512,
    ...                                   "rnn_layers": 1,
    ...                                   "reproject_words": True,
    ...                                   "reproject_words_dimension": 256,
    ...                                   "bidirectional": False,
    ...                                   "dropout": 0.5,
    ...                                   "word_dropout": 0.0,
    ...                                   "locked_dropout": 0.0,
    ...                                   "rnn_type": "GRU",
    ...                                   "fine_tune": True, },
    ...                  }
    ```
    """

    __allowed_methods = ["rnn", "pool"]
    __allowed_configs = ("pool_configs", "rnn_configs")

    def __init__(
        self,
        *embeddings: str,
        methods: List[str] = ["rnn", "pool"],
        configs: Dict = {
            "pool_configs": {"fine_tune_mode": "linear", "pooling": "mean"},
            "rnn_configs": {
                "hidden_size": 512,
                "rnn_layers": 1,
                "reproject_words": True,
                "reproject_words_dimension": 256,
                "bidirectional": False,
                "dropout": 0.5,
                "word_dropout": 0.0,
                "locked_dropout": 0.0,
                "rnn_type": "GRU",
                "fine_tune": True,
            },
        },
    ):
        print("May need a couple moments to instantiate...")
        self.embedding_stack = []

        # Check methods
        for m in methods:
            assert m in self.__class__.__allowed_methods

        # Set configs for pooling and rnn parameters
        for k, v in configs.items():
            assert k in self.__class__.__allowed_configs
            setattr(self, k, v)

        # Load correct Embeddings module
        for model_name_or_path in embeddings:
            self.embedding_stack.append(_get_embedding_model(model_name_or_path))

        assert len(self.embedding_stack) != 0
        if "pool" in methods:
            self.pool_embeddings = DocumentPoolEmbeddings(
                self.embedding_stack, **self.pool_configs
            )
            print("Pooled embedding loaded")
        if "rnn" in methods:
            self.rnn_embeddings = DocumentRNNEmbeddings(
                self.embedding_stack, **self.rnn_configs
            )
            print("RNN embeddings loaded")

    def embed_pool(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        detail_level:DetailLevel = DetailLevel.Low,
    ) -> List[EmbeddingResult]:
        """Generate stacked embeddings with `DocumentPoolEmbeddings`

        **Parameters**:
        * `text` - Text input, it can be a string or any of Flair's `Sentence` input formats
        * `detail_level` - A level of detail to return. By default is None, which returns a EmbeddingResult, otherwise will return a dict

        **Return**:
        * A list of either EmbeddingResult's or dictionaries with information
        """
        sentences = _make_sentences(text, as_list=True)
        self.pool_embeddings.embed(sentences)
        return _format_results(sentences, detail_level)

    def embed_rnn(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        detail_level:DetailLevel = DetailLevel.Low,
    ) -> List[Sentence]:
        """Generate stacked embeddings with `DocumentRNNEmbeddings`

        **Parameters**:
        * `text` - Text input, it can be a string or any of Flair's `Sentence` input formats
        * `detail_level` - A level of detail to return. By default is None, which returns a EmbeddingResult, otherwise will return a dict

        **Return**:
        * A list of either EmbeddingResult's or dictionaries with information
        """
        sentences = _make_sentences(text, as_list=True)
        self.rnn_embeddings.embed(sentences)
        return _format_results(sentences, detail_level)