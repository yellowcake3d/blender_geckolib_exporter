# blender_geckolib_exporter
It's a vibe coded blender 3.6 addon that can export blender keyframes to geckolib animations

How it works:
1. Create a geckolib model in blockbench
2. Assign the things you wanted to animate to bones (put them in folders in BB) and place the origin point at the most convenient place. Do not parent bones to other bones (do not put folders in folders)
3. Export the model with FBX, in the settings turn off export animations, and instead of ASCII use Binary experimental mode.
4. Import the fbx model in blender
5. The bones from blockbench turned into empty obejcts, with corresponding parented cubes
6. do the necessary animations, you can parent the empties to other things, use constraints, etc.
7. Bake the animation (select all the empties, Object -> Animation -> Bake action -> Select all checkmarks -> Click OK)
8. Select all the empties -> Object -> Animation -> Export to json
9. Now, there's trial and error. If it was a good addon, ideally all you needed to do from now on was choose XZY in swap xyz for scale rotation and location, and click export. Also maybe turn on 0 rotation and normalize scale at start. In practice, it's an ai generated addon, which means it's garbage. If the animation's location is inverted for some reason, press checkmarks for axis inversion and try exporting. If the model suddenly turns 180 degrees and then back, try to turn on the closest axis unwrap. Anything barely works? Yeah, I know...
10. After you exported a txt file, rename it to .json, in blockbench animation tab press import animations, choose your json file, and hopefully it works.

Why did I publish this addon if I know it's trash?
People were curious how it works and expressed interest in maybe improving it. If you're planning to use it for your animations, good luck lol
