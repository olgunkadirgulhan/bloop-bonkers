"""Karakter replikleri: her durum için (normal, psikopat) tek satır + anime ünlemleri.
Sesleri gecmiste-sen/tools/voice_lib.py (Gemini TTS) bir kez üretir → voices/<ses>/...; bloop.build_audio çalar."""

LINES = {
    'cookie': ('Just one cookie. Nice.', 'ALL the cookies are mine!'),
    'alarm': ('Good morning, alarm!', 'Silence, you evil clock!'),
    'ketchup': ('A little ketchup, please.', 'Ketchup on EVERYTHING!'),
    'cake': ('Make a wish!', 'The whole cake is mine!'),
    'soda': ('Ahh, refreshing.', 'Shake it first! Hehe!'),
    'icecream': ('One scoop, please.', 'Brain freeze? Worth it!'),
    'balloon': ('Let me blow it up.', 'Bigger! BIGGER!'),
    'pumpkin': ('A cute little face.', 'Spooky time! Mwahaha!'),
    'coffee': ('Coffee time. Mmm.', 'Ten coffees! I can see sounds!'),
    'gum': ('Small bubble. Cute.', 'The biggest bubble ever!'),
    'popcorn': ('Movie night snack.', 'Popcorn rain! Open wide!'),
    'toothpaste': ('Brush, brush, brush.', 'The whole tube! Sparkle!'),
    'sandwich': ('A nice little sandwich.', 'Sandwich tower! Fifty floors!'),
    'gift': ('Oh, a present! Thank you!', 'Rip it open! NOW!'),
    'pizza': ('Mmm, one slice.', 'The whole pizza. One bite.'),
    'phone': ('Charging up. Patience.', 'Charge faster, you brick!'),
    'plant': ('A little water for you.', 'Grow, plant! GROW!'),
    'chips': ('Just a few chips.', 'Pour the whole bag in!'),
    'lemon': ('Fresh lemonade!', 'Lemon straight up! Sour!'),
    'donut': ('Breakfast donut. Yum.', 'Donut tower! Breakfast of champions!'),
    'sneeze': ('Excuse me. Achoo.', 'ACHOOOOO! Sorry, everyone!'),
    'spaghetti': ('Twirl, twirl, bite.', 'Slurp it all at once!'),
    'selfie': ('Smile for the photo!', 'A thousand selfies! Again!'),
    'hotsauce': ('Just one drop.', 'The whole bottle! Fire!'),
    'umbrella': ('Good thing I brought this.', 'Rain? I love rain!'),
    'pancake': ('Flip it gently.', 'Flip it to the ceiling!'),
    'cereal': ('Cereal, then milk.', 'Milk first! Chaos!'),
    'egg': ('Crack it softly.', 'Smash the egg! Yolk everywhere!'),
    'watermelon': ('One juicy slice.', 'The whole melon! Let us go!'),
    'dumbbell': ('Nice and steady.', 'One thousand reps! Power!'),
    'fan': ('Ahh, cool breeze.', 'Maximum speed! Wheee!'),
    'banana': ('Peel it nicely.', 'Banana! In one bite!'),
    'paperplane': ('Fly, little plane!', 'Turbo paper jet! Launch!'),
    'pen': ('Click. Write. Done.', 'Click click click click!'),
    'toast': ('Golden toast. Perfect.', 'Toast launch! Catch it!'),
    'yoyo': ('Up and down.', 'Yo-yo tornado!'),
    'tissue': ('One tissue, please.', 'The whole box! Achoo!'),
    'mosquito': ('Shoo, little bug.', 'Come here, you tiny vampire!'),
    'nap': ('Just a short nap.', 'Sleep mode! Zzz... forever!'),
    'basket': ('Nice and easy shot.', 'Three-pointer! From space!'),
    'tape': ('Neat and tidy box.', 'Tape! Tape everything!'),
    'piano': ('A gentle melody.', 'Piano rock concert!'),
    'cactus': ('Careful with the spikes.', 'Hug the cactus! Ouch!'),
    'hotdog': ('Mustard, a little.', 'Hot dog! Tower edition!'),
    'boba': ('Sip, sip. Yummy.', 'Boba bullets! Pew pew!'),
    'cards': ('Careful... steady...', 'Card tower to the moon!'),
    'phonecall': ('Hello? How are you?', 'WHO IS THIS?!'),
    'scratch': ('Let us see. Fingers crossed.', 'Scratch it! I am rich!'),
    'shoelace': ('A nice little bow.', 'Super mega knot!'),
    'bottleflip': ('One try. Here goes.', 'Flip! Flip! Flip!'),
    'candybowl': ('Take one, please!', 'All the candy is mine!'),
    'costume': ('A cute costume.', 'Scariest costume ever!'),
    'microwave': ('Thirty seconds. Ding.', 'Ninety minutes! Boom!'),
    'doorbell': ('Coming! One moment!', 'Who dares ring my bell?!'),
    'fridge': ('Just a little snack.', 'Eat the whole fridge!'),
    'laundry': ('Fold it neatly.', 'Laundry mountain! Dive!'),
    'chess': ('Hmm, your move.', 'Checkmate! Flip the board!'),
    'karaoke': ('La la la, nice song.', 'MAXIMUM VOLUME!'),
    'skate': ('Slow and careful.', 'Kickflip! Mega jump!'),
    'candle': ('Mmm, smells nice.', 'Light them all! Fire party!'),
    'darts': ('Aim... and throw.', 'Bullseye! Ten at once!'),
    'dishes': ('Wash, rinse, done.', 'Bubble storm! Splash!'),
}

# tür → ünlemler (tür = bloop.build_audio içindeki tepki anı)
EXCLAIM = {
    'hm': ['Hmm?', 'Ehhh?', 'Ara?', 'Huh?', 'Oh?'],
    'yell': ['Nani?!', 'Kyaaa!', 'Uwaaah!', 'Yamete!', 'Noooo!', 'Itai!', 'Wait, what?!'],
    'giggle': ['Hehehe!', 'Fufufu...', 'Ufufu!', 'Kihihi!'],
    'yay': ['Yatta!', 'Sugoi!', 'Oishii!', 'Yaaay!', 'Kawaii!', 'Ganbatte!'],
    'evil': ['Mwahahaha!', 'Kukuku...', 'Ohohoho!'],
    'talk': ['Itadakimasu!', 'Hmph!', 'Hayaku!', 'Mou!', 'Ikuzo!', 'Ne, ne!', 'Daijoubu?', 'Oops!'],
}

# karakter → ses: kız karakterler Zephyr, diğerleri Puck (Leda/Fenrir çılgın tonda Whisper doğrulamasını geçemedi)
FEMALE = {'mimi', 'luna', 'nova', 'pepper', 'jojo', 'kiki'}


def voices_for(cast):
    """(replik sesi, ünlem sesi)"""
    return ('Zephyr', 'Zephyr') if cast in FEMALE else ('Puck', 'Puck')
