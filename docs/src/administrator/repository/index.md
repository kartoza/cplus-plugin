<html>
<head>
</head>

<body>
<div id="loading_div" style="align-content: center;">

<img src="https://kartoza.github.io/cplus-plugin/user/guide/img/icon_loading.gif" style="align-content: center; background:transparent;"/>
</div>
<div>
    <h2><a href="#pull"> Pull requests artifacts </a></h2>
</div>
<div id="pull_artifacts">
    <table>
        <thead>
        <tr>
        <th>PR title</th>
        <th>PR url</th>
        <th>Artifact name</th>
        <th>Artifact link</th>
        <th>Created date</th>
        </tr>
        </thead>

        <tbody id="pulls_tbody">
        </tbody>
    </table>
</div>

<div>
    <h2><a href="#main"> Main branch artifacts </a></h2>
</div>
<div id="main_artifacts">
    <table>
        <thead>
        <tr>
        <th>Commit link</th>
        <th>Artifact name</th>
        <th>Artifact link</th>
        <th>Created date</th>
        </tr>
        </thead>

        <tbody id="main_tbody">
        </tbody>
    </table>
</div>

</body>

<script type="module">
import { Octokit, App } from "https://esm.sh/octokit";
const octokit = new Octokit();

const pulls = await octokit.request(
"GET /repos/kartoza/cplus-plugin/pulls",
{'state':'all'}
);

const fetched_artifacts = await octokit.request(
"GET /repos/kartoza/cplus-plugin/actions/artifacts",
{'per_page': 30}
);

const pulls_artifacts = [];
const commits_artifacts = [];

const artifacts_comments = [];


for ( const pull of pulls.data ){
    const head_sha = pull['head']['sha'];
    const pull_artifact = {};
    const artifact_comments = [];

    if (pull == undefined)
        continue;

    for ( const artifact of fetched_artifacts.data.artifacts){

        if ( artifact['workflow_run']['head_sha'] == head_sha &&
            artifact['name'].indexOf('cplus_plugin') != -1 ){
            pull_artifact['pull'] = pull;
            pull_artifact['artifact'] = artifact;
            artifact_comments['artifact'] = artifact;
            artifact_comments['comments'] = pull['comments_url'];
            
        }
    }
    pulls_artifacts.push(pull_artifact);
    artifacts_comments.push(artifact_comments);
}

for ( const artifact of fetched_artifacts.data.artifacts){

    if ( artifact['name'].indexOf('cplus_plugin') == -1){
        continue;
    }
    const commit = await octokit.request(
    "GET /repos/kartoza/cplus-plugin/commits/"+
    artifact['workflow_run']['head_sha'] 
    );

    if ( commit == undefined | commit.data.parents.length < 2 ){
        continue;
    }

    const commit_artifact = {
        'commit': commit,
        'artifact': artifact
    };

    commits_artifacts.push(commit_artifact);
}

const pulls_tbody = document.getElementById('pulls_tbody');
const main_tbody = document.getElementById('main_tbody');

for (const pull_artifact of pulls_artifacts){

        if (pull_artifact['pull'] == undefined)
        {
            continue;
        }

     const tr = document.createElement('tr');
     const first_td = document.createElement('td');
     const second_td = document.createElement('td');
     const third_td = document.createElement('td');
     const fourth_td = document.createElement('td');
     const fifth_td = document.createElement('td');

     const pull_link = document.createElement("a");
     const link_node = document.createTextNode(
      pull_artifact['pull']['title']
      );

     pull_link.appendChild(link_node);
     pull_link.textContent = pull_artifact['pull']['html_url'];
     pull_link.title = pull_artifact['pull']['html_url'];
     pull_link.href = pull_artifact['pull']['html_url'];

     first_td.appendChild(link_node);
     second_td.appendChild(pull_link);

     tr.appendChild(first_td);
     tr.appendChild(second_td);

     const artifact_link = document.createElement("a");
     const second_link_node = document.createTextNode(
        pull_artifact['artifact']['name']
     );
     const date_node = document.createTextNode(
        pull_artifact['artifact']['created_at']
     );
     artifact_link.appendChild(second_link_node);
     artifact_link.textContent = pull_artifact['artifact']['archive_download_url'];
     artifact_link.href = pull_artifact['artifact']['archive_download_url'];
     artifact_link.id = pull_artifact['artifact']['name'];

     third_td.appendChild(second_link_node);
     fourth_td.appendChild(artifact_link);
     fifth_td.appendChild(date_node);

     tr.appendChild(third_td);
     tr.appendChild(fourth_td);
     tr.appendChild(fifth_td);

     pulls_tbody.appendChild(tr)
}

for( const artifact_comment of artifacts_comments){
    if (artifact_comment['comments'] === undefined)
        continue;
    const comments = await fetch(artifact_comment['comments']);

    const result = comments.json().then(function(results){
        for(const comment of results){
            if (comment.body.indexOf("Download the plugin zip file here") != -1){
                const artifact_link_regex = /(https?:\/\/[^ ]*)/;
                const matches = comment.body.match(artifact_link_regex);
                const art_link = matches[0];

                const artifact_name = artifact_comment['artifact']['name'];
                const artifact_url = art_link.split("\n")[0];
        
                const pull_artifact = document.getElementById(artifact_name);
        
                if( pull_artifact == undefined){
                    continue;
                }
                pull_artifact.textContent = artifact_url;
                pull_artifact.href = artifact_url;
            }
        }
    })
}


for (const commit_artifact of commits_artifacts){

     if (commit_artifact['commit'] === undefined)
         continue;

     const tr = document.createElement('tr');
     const first_td = document.createElement('td');
     const second_td = document.createElement('td');
     const third_td = document.createElement('td');
     const fourth_td = document.createElement('td');
     const fifth_td = document.createElement('td');

     const pull_link = document.createElement("a");
     const link_node = document.createTextNode(
        commit_artifact['commit']['data']['sha']
     );

     pull_link.appendChild(link_node);
     pull_link.textContent = commit_artifact['commit']['data']['html_url'];
     pull_link.title = commit_artifact['commit']['data']['html_url'];
     pull_link.href = commit_artifact['commit']['data']['html_url'];

     first_td.appendChild(link_node);
     second_td.appendChild(pull_link);

     tr.appendChild(second_td);

     const artifact_link = document.createElement("a");
     const second_link_node = document.createTextNode(
        commit_artifact['artifact']['name']
     );
     const date_node = document.createTextNode(
        commit_artifact['artifact']['created_at']
     );
     artifact_link.appendChild(second_link_node);
     artifact_link.textContent = commit_artifact['artifact']['archive_download_url'];
     artifact_link.href = commit_artifact['artifact']['archive_download_url'];

     third_td.appendChild(second_link_node);
     artifact_link.id = commit_artifact['artifact']['name'];
     fourth_td.appendChild(artifact_link);
     fifth_td.appendChild(date_node);

     tr.appendChild(third_td);
     tr.appendChild(fourth_td);
     tr.appendChild(fifth_td);

     main_tbody.appendChild(tr)

}

const response = await fetch(
"https://raw.githubusercontent.com/kartoza/cplus-plugin/docs/docs/admin/artifacts_list.txt"
);

const file_text_promise = response.text();

const res = file_text_promise.then(function(result){
    const art_list = result.split("\n");

    for( const art of art_list){
        if( art === ""){
            continue;
        }
        const parts = art.split(" - ");
        const artifact_name = parts[0].trim();
        const artifact_url = parts[1].trim();

        const main_artifact = document.getElementById(artifact_name);

        if( main_artifact == undefined){
            continue;
        }
        main_artifact.textContent = artifact_url;
        main_artifact.href = artifact_url;
    }

    const loading_div = document.getElementById('loading_div');
    loading_div.remove();
});


</script>

</html>
