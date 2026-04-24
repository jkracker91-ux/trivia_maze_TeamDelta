Trivia Maze — Docker build and run
====================================

Docker Hub image (after you build and push with push-to-dockerhub.sh)
----------------------------------------------------------------------
  Replace YOUR_DOCKER_HUB_USERNAME with your Docker Hub ID (lowercase).

  Image names:
    YOUR_DOCKER_HUB_USERNAME/maze:v1
    YOUR_DOCKER_HUB_USERNAME/maze:latest

  Example pull and run (interactive CLI):
    docker pull YOUR_DOCKER_HUB_USERNAME/maze:v1
    docker run --rm -it YOUR_DOCKER_HUB_USERNAME/maze:v1

  The container clones the GitHub repo at build time and runs: python main.py


Build locally (from the repository root)
----------------------------------------
  docker build -f Dockerfiles/Dockerfile -t maze:latest .

  docker run --rm -it maze:latest


Build with Docker Compose (from the repository root)
--------------------------------------------------
  docker compose -f Dockerfiles/docker-compose.yml build
  docker compose -f Dockerfiles/docker-compose.yml run --rm maze


Push your local image to Docker Hub
-----------------------------------
  docker login
  export DOCKER_USERNAME=YOUR_DOCKER_HUB_USERNAME
  ./Dockerfiles/push-to-dockerhub.sh

  That tags maze:latest as YOUR_DOCKER_HUB_USERNAME/maze:latest and :v1,
  then pushes both tags to Docker Hub.