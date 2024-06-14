:tada:**Announcing DocDocGo version 0.2**:tada:

DocDocGo is growing up! Let's celebrate by describing the new features.

**1. DDG finally has a logo that's not just the 🦉 character!**

Its [design](https://github.com/reasonmethis/docdocgo-core/blob/7239a9ad9ac4756fced7d8931d1a4b1bba118a8a/media/minimal13.svg) continues the noble tradition of trying too hard to be clever, starting with the name "DocDocGo" :grin:

@StreamlitTeam continues to ship - the new `st.logo` feature arrived just in time!

**2. Re-engineered collections**

With over 150 public collections and growing, it was time to manage them better. Now, collections track how recently they were created/updated. Use:

- `/db list` - see the 20 most recent collections (in a cute table)

- `/db list 21+` - see the next 20, and so on

- `/db list blah` - list collections with "blah" in the name

DDG will remind you of the availablej commands when you use `/db` or `/db list`.

**Safety improvement:** Deleting a collection by number, e.g. `/db delete 42`, now only works if it was first listed by `/db list`.

**3. Default modes**

Tired of typing `/reseach` or `/research heatseek`? Let your fingers rest by selecting a default mode in the Streamlit sidebar.

You can still override it when you need to - just type the desired command as usual, for example: `/help What's the difference between regular research and heatseek?`.

**4. UI improvements**

The UI has been refreshed with a new intro screen that has:

- The one-click sample commands to get you started if you're new

- The new and improved welcome message

Take the new version for a spin and let me know what you think! :rocket:

https://docdocgo.streamlit.app
