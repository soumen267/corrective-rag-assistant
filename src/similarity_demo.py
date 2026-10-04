import numpy as np

from embeddings import get_embedding_model


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    a = np.array(vector_a)
    b = np.array(vector_b)

    return float(
        np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    )


if __name__ == "__main__":
    embedding_model = get_embedding_model()

    query = "How does Laravel inject dependencies?"

    texts = [
        "Laravel's service container manages class dependencies.",
        "Laravel middleware filters HTTP requests.",
        "MySQL is a relational database management system.",
        "Dogs enjoy playing outside.",
    ]

    query_vector = embedding_model.embed_query(query)
    document_vectors = embedding_model.embed_documents(texts)

    for text, vector in zip(texts, document_vectors):
        score = cosine_similarity(query_vector, vector)

        print(f"{score:.4f} | {text}")