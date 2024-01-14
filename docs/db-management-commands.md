# Database Management Commands

You can use the following commands to manage your collections:

- `/db list`: list all your collections
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"

Additional shorthands:

- `/db use 3`: switch to collection #3 in the list
- `/db delete 3, 42, 12`: delete collections #3, #42, and #12 (be careful!)
- `/db delete --current` (or just `-c`): delete the current collection
