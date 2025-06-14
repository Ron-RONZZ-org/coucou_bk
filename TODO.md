## Fonctionnalités

### Tout essentiel

[X] Ajouter les éléments
[X] Afficher les éléments par date
[X] Raccourcis clavier: record_manager Ctrl+S, DELETE, CTRL+F, CTRL+G main BOUTONs,
[X] Abilité de signaler erreur pendant révision
[X] Musique de célébration après tout fait ! 

### Les cerises sur la gâteau

[X!!] le coupement de l'audio original et l'addition de questions et réponses multiples.  
    [] accepter audio path (mémoriser pour prochaines entrées jusqu'à changé par utilisateur)
    [] permettre couper sonne par timestamp 
    [] permettre utilisateur de saisir questions ([]) et réponses ([]) : multiple dans listes
        [] backward compatibilité essentiel avec questions et réponses comme strings déjà présentents dans la base de données
    [] enter > saisir prochaine entrée, jusqu'à utilisateur quitte par CTRL+W ou la croix. 
    [] enregister en la base de données
[] Compilation
    [] Android
        https://doc.qt.io/qtforpython-6/deployment/index.html#deployment-guides
        https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-android-deploy.html#pyside6-android-deploy

### peut-être ?

[] Tagging, catégorisation des emsembles par topique
[] Web semantique: nested tags & SPARQL

## commandes fréquents

```bash
eval "$(poetry environment activate)"
```

```bash
serial=10
file_name=0tatoeba-$serial.csv
cp 0tatoeba-template.csv $file_name
code $file_name
``` 

```SQL
ALTER TABLE records RENAME COLUMN audio_file TO media_file;
ALTER TABLE records RENAME COLUMN custom_audio TO custom_media;
ALTER TABLE records ADD COLUMN attribution TEXT NOT NULL DEFAULT 'no-attribution';
```

```bash
git add .
git commit -m "1.0 release" -a
git push -u origin main --force-with-lease
```

## Non utilisés

```bash
date="2025-05-17"
s="/media/ron/Ronzz_Core/nextCloudSync/mindiverse-life/coucou/coucou/vocab_$date.csv"
cp template.csv "$s"
nohup libreoffice --calc "$s" &>/dev/null &
```

```bash
date="2025-05-15"
s="/media/ron/Ronzz_Core/nextCloudSync/mindiverse-life/coucou/coucou/vocab_$date.csv"
nohup libreoffice --calc "$s" &>/dev/null &
```

```bash
nohup libreoffice --calc "/media/ron/Ronzz_Core/nextCloudSync/lib/leMondeEnLesCartes/assets/images/éléments de français.csv" &
```

```txt
vérifér l'orthographe des mots.Début mots en minuscule sauf phrase entière en majuscule. Pour les noms, ajouter "un/une" avant les noms singulier, "les" avant les pluriels quand il n'y a pas. Pour les adjectifs, vérifier que ils sont en forme pour les nom singulier masculin. Supprimer les espace supplémentaires.
```

