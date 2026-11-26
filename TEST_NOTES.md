# Testing notes
These notes are filled by Tom after he plays on the piano. These serve as input for the next steps in developing the application.

## Remarks
- Connecting or selecting the keyboard after the application started gives strange results. I think this needs a test because I'm not sure what happens.
- Please keep track of accuracy and show it in the top-left corner next to the tempo ... 
- After performing correctly twice at 100% please ask if I want to do it again or if I want to proceed. Let me practice again at 100% by playing a C and proceed with the next by playing an F. Mention the accuracy, so I can make a good decision.
- The on-screen notifications are a bit wierd there are several kinds and they don't have a common place. Please make 1 type of notification, make sure that it's not overlapped by the count-in and display all messages there. Also make sure that the messages are "user-facing" not development speech leaking into the ui. Make them a bit interesting and fun. Examples:
  - New tempo
  - New hand
  - New section
  - Show accuracy in the relevant messages
  - Try again... 
  - Well done: xx% accuracy!
  - Try again: xx% accuracy!
  - Etc.
- Once we have a good measure for accuracy I will ask you to also force retry on low accuracy, you can add that functionality now, but I have to find a good value for it, so please let it always pass now (i.e. even 0% accuracy passes) and later we can increase it. But this is seperate from missed notes, missed notes or wrong notes always trigger a retry. 
- For the non-tempo play, please be more tollerant regarding when the note can be pressed, now the bar really needs to be stopped, that's not necessary, though we should check if we are somewhat in range of the note, but not too strict.
- After the first measure, the key-signature and cleff symbols are no longer shown which is problematic because we need to know them for each practice session, so please just always show them.
- In the Pathetique sonata for the first measures I still have to play the left-hand two quater notes starting at 50%, my god that takes a long time :) So we need to also calculate this base tempo because this is just annoying when it takes so long just to play two notes.
- When the application switches from 1 hand to 2 hands, and switches from 1 section to another there is a visual blink that kind of moves everything on screen. But the application should never blink or suddenly change, the bar should just keep moving.
- Notes in the small measure in the lower-right-hand corner sometimes 'stick' they never get removed even though the notes are no longer held.
