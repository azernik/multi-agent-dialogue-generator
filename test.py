from toon import encode

# Simple object
data = {"name": "Alice", "age": 30}
print(encode(data))
# Output:
# name: Alice
# age: 30

# Tabular array (uniform objects)
users = [
    {"id": 1, "name": "Alice", "age": 30},
    {"id": 2, "name": "Bob", "age": 25},
    {"id": 3, "name": "Charlie", "age": 35},
]
print(encode(users))
# Output:
# [3,]{id,name,age}:
#   1,Alice,30
#   2,Bob,25
#   3,Charlie,35

# Complex nested structure
data = {
    "metadata": {"version": 1, "author": "test"},
    "items": [
        {"id": 1, "name": "Item1"},
        {"id": 2, "name": "Item2"},
    ],
    "tags": ["alpha", "beta", "gamma"],
}
print(encode(data))
# Output:
# metadata:
#   version: 1
#   author: test
# items[2,]{id,name}:
#   1,Item1
#   2,Item2
# tags[3]: alpha,beta,gamma