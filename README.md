# TruelyTerribleTrivia
A Discord trivia bot



## Classes

+ **Trivia Bot**: Actual bot class inheriting from discord.client. Manages games and building question lists. 
+ **QuestionFetcher**: Abstract class for fetching questions
    - **OpenTriviaFetcher**: Implements QuestionFetcher and fetches questions from opentdb
    - **LocalFetcher**: ImplementsQuestionFetcher and fetches questions from local file system
+ **TriviaGame**: Abstract class, common elements of a trivia game
    - **MultiChoiceFFA**: Multiple choice free for all game. 
    - **TrueFalseFFA**: True/False free for all game. 
    - **FreeResponseFFA**: First to guess within 1 levenshtein distance
    - **JeopardyClone**: Gotta come up with a better name. The idea is as follows
      - 5 categories, 2 easy, 2 medium, 2 hard for each, 30 total questions
        - Randomly chosen categories
      - like jeopardy there's a daily double
      - scores tracked via points scaled to difficulty
        - 100 for easy, 200 for medium 400 for hard etc. Obviously needs balancing

## Other Requirements

- configurable game sounds
  - "killstreaks" for sequential question wins
  - victory sound for player that won

